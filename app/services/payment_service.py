from __future__ import annotations
import os
import hmac
import hashlib
from datetime import datetime, timedelta
from app.extensions import db
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.models.user import User

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")

PLANS = {
    "free": {
        "name": "Free",
        "price": 0,
        "currency": "INR",
        "features": [
            "3 resumes",
            "3 versions per resume",
            "ATS scoring",
            "PDF export",
        ],
        "limits": {
            "max_resumes": 3,
            "max_versions": 3,
            "ai_enabled": False,
        },
    },
    "pro": {
        "name": "Pro",
        "price": 2900,
        "currency": "INR",
        "features": [
            "Unlimited resumes",
            "Unlimited versions",
            "AI features",
            "All export formats",
            "Job matching",
            "Priority support",
        ],
        "limits": {
            "max_resumes": -1,
            "max_versions": -1,
            "ai_enabled": True,
        },
    },
    "enterprise": {
        "name": "Enterprise",
        "price": 199900,
        "currency": "INR",
        "features": [
            "Everything in Pro",
            "Recruiter dashboard",
            "Team features",
            "Custom integrations",
            "Dedicated support",
        ],
        "limits": {
            "max_resumes": -1,
            "max_versions": -1,
            "ai_enabled": True,
        },
    },
}


class PaymentService:

    @staticmethod
    def get_plans() -> dict:
        return {"plans": PLANS}

    @staticmethod
    def create_razorpay_order(user_id: int, plan: str) -> dict:
        if plan not in PLANS:
            return {"success": False, "error": "Invalid plan"}

        amount = PLANS[plan]["price"]

        if not RAZORPAY_KEY_ID:
            return {
                "success": True,
                "order_id": f"demo_order_{user_id}_{plan}",
                "amount": amount,
                "currency": "INR",
                "key_id": "demo_key",
                "plan": plan,
                "note": "Razorpay not configured — demo mode",
            }

        try:
            import razorpay
            client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
            order = client.order.create({
                "amount": amount,
                "currency": "INR",
                "payment_capture": 1,
                "notes": {"user_id": str(user_id), "plan": plan},
            })
            return {
                "success": True,
                "order_id": order["id"],
                "amount": amount,
                "currency": "INR",
                "key_id": RAZORPAY_KEY_ID,
                "plan": plan,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def verify_razorpay_payment(
        user_id: int, payment_id: str, order_id: str, signature: str
    ) -> dict:
        if not RAZORPAY_KEY_SECRET:
            return PaymentService._activate_subscription(user_id, "pro", payment_id, order_id)

        body = f"{order_id}|{payment_id}"
        expected = hmac.new(
            RAZORPAY_KEY_SECRET.encode(), body.encode(), hashlib.sha256
        ).hexdigest()

        if hmac.compare_digest(expected, signature):
            return PaymentService._activate_subscription(user_id, "pro", payment_id, order_id)
        return {"success": False, "error": "Invalid signature"}

    # ═══════════════════════════════════════════════════════════
    # FIXED: resume_limit/version_limit = 999 instead of -1
    # (Database constraint: >= 0, so 999 = practically unlimited)
    # ═══════════════════════════════════════════════════════════
    @staticmethod
    def _activate_subscription(
        user_id: int, plan: str, payment_id: str, order_id: str
    ) -> dict:
        """Internal: Create payment record + activate subscription."""
        existing = Subscription.query.filter_by(user_id=user_id).first()

        now = datetime.utcnow()
        if existing:
            existing.plan_type = plan
            existing.status = "active"
            existing.starts_at = now
            existing.current_period_start = now
            existing.current_period_end = now + timedelta(days=30)
            existing.resume_limit = 999 if plan in ("pro", "enterprise") else 3
            existing.version_limit = 999 if plan in ("pro", "enterprise") else 3
            existing.ai_enabled = plan in ("pro", "enterprise")
            existing.recruiter_access = plan == "enterprise"
        else:
            sub = Subscription(
                user_id=user_id,
                plan_type=plan,
                status="active",
                provider="razorpay",
                starts_at=now,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                resume_limit=999 if plan in ("pro", "enterprise") else 3,
                version_limit=999 if plan in ("pro", "enterprise") else 3,
                ai_enabled=plan in ("pro", "enterprise"),
                recruiter_access=plan == "enterprise",
            )
            db.session.add(sub)

        payment = Payment(
            user_id=user_id,
            provider="razorpay",
            provider_payment_id=payment_id,
            provider_order_id=order_id,
            amount_cents=PLANS[plan]["price"],
            currency="INR",
            status="paid",
            provider_payload={"source": "razorpay_verify"},
        )
        db.session.add(payment)
        db.session.commit()

        return {"success": True, "message": f"Subscription activated: {plan}", "plan": plan}

    @staticmethod
    def handle_payment_webhook(data: dict) -> dict:
        """Generic webhook — logs payment only. Admin must manually verify."""
        user_id = data.get("user_id") or data.get("CUST_ID")
        amount = data.get("amount") or data.get("TXNAMOUNT") or data.get("amount_cents", 0)
        transaction_id = (
            data.get("transaction_id")
            or data.get("payment_id")
            or data.get("TXNID")
            or data.get("ORDERID")
            or data.get("id")
        )
        provider = data.get("provider", "upi")
        status = data.get("status") or data.get("STATUS") or data.get("TXNSTATUS", "paid")
        plan = data.get("plan", "pro")

        if not user_id or not transaction_id:
            return {"success": False, "error": "Missing user_id or transaction_id"}

        existing = Payment.query.filter_by(
            provider=provider, provider_payment_id=str(transaction_id)
        ).first()
        if existing:
            return {
                "success": True,
                "message": "Payment already recorded",
                "payment_id": existing.id,
            }

        if isinstance(amount, str):
            amount = float(amount)
        if amount < 100:
            amount_cents = int(amount * 100)
        else:
            amount_cents = int(amount)

        is_paid = status in ("paid", "success", "captured", "complete", "TXN_SUCCESS")
        payment = Payment(
            user_id=int(user_id),
            provider=provider,
            provider_payment_id=str(transaction_id),
            amount_cents=amount_cents,
            currency="INR",
            status="paid" if is_paid else "pending",
            paid_at=datetime.utcnow() if is_paid else None,
            provider_payload=data,
        )
        db.session.add(payment)
        db.session.commit()

        return {
            "success": True,
            "message": "Payment logged. Admin must manually activate subscription.",
            "payment_id": payment.id,
            "note": "Subscription NOT auto-activated.",
        }

    # ═══════════════════════════════════════════════════════════
    # FIXED: resume_limit/version_limit = 999 instead of -1
    # ═══════════════════════════════════════════════════════════
    @staticmethod
    def activate_subscription_manually(
        user_id: int, plan: str = "pro", admin_user_id: int = None
    ) -> dict:
        """Admin manually activates subscription for any user — no payment required."""
        user = User.query.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        Subscription.query.filter_by(user_id=user_id, status="active").update(
            {"status": "canceled", "canceled_at": datetime.utcnow()}
        )

        now = datetime.utcnow()
        sub = Subscription(
            user_id=user_id,
            plan_type=plan,
            status="active",
            provider="internal",
            starts_at=now,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            resume_limit=999 if plan in ("pro", "enterprise") else 3,
            version_limit=999 if plan in ("pro", "enterprise") else 3,
            ai_enabled=plan in ("pro", "enterprise"),
            recruiter_access=plan == "enterprise",
        )
        db.session.add(sub)
        db.session.commit()

        return {
            "success": True,
            "message": f"Subscription manually activated: {plan}",
            "plan": plan,
        }

    @staticmethod
    def deactivate_subscription(user_id: int) -> dict:
        """Cancel active subscription."""
        sub = Subscription.query.filter_by(user_id=user_id, status="active").first()
        if not sub:
            return {"success": False, "error": "No active subscription found"}

        sub.status = "canceled"
        sub.canceled_at = datetime.utcnow()
        db.session.commit()

        return {"success": True, "message": "Subscription deactivated"}

    @staticmethod
    def handle_razorpay_webhook(payload: str, signature: str) -> dict:
        if not RAZORPAY_KEY_SECRET:
            return {"success": True, "note": "Demo mode"}
        try:
            expected = hmac.new(
                RAZORPAY_KEY_SECRET.encode(), payload.encode(), hashlib.sha256
            ).hexdigest()
            if hmac.compare_digest(expected, signature):
                return {"success": True}
            return {"success": False, "error": "Invalid signature"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_user_subscription(user_id: int) -> dict:
        sub = Subscription.query.filter_by(user_id=user_id).order_by(
            Subscription.created_at.desc()
        ).first()
        if not sub:
            return {
                "plan": "free",
                "status": "active",
                "limits": PLANS["free"]["limits"],
            }
        return {
            "plan": sub.plan_type,
            "status": sub.status,
            "started_at": sub.starts_at.strftime("%d %b %Y") if sub.starts_at else None,
            "expires_at": sub.current_period_end.strftime("%d %b %Y")
            if sub.current_period_end else None,
            "limits": PLANS.get(sub.plan_type, PLANS["free"])["limits"],
        }

    @staticmethod
    def cancel_subscription(user_id: int) -> dict:
        sub = Subscription.query.filter_by(user_id=user_id).order_by(
            Subscription.created_at.desc()
        ).first()
        if not sub:
            return {"success": False, "error": "No subscription"}
        sub.status = "canceled"
        sub.canceled_at = datetime.utcnow()
        db.session.commit()
        return {"success": True, "message": "Subscription cancelled"}

    @staticmethod
    def create_stripe_session(user_id: int, plan: str) -> dict:
        return {"success": True, "session_id": "mock_stripe_session", "url": "/dashboard"}

    @staticmethod
    def verify_stripe_payment(user_id: int, session_id: str) -> dict:
        return PaymentService._activate_subscription(user_id, "pro", "stripe_pay_123", "stripe_ord_123")

    @staticmethod
    def handle_stripe_webhook(payload: str, signature: str) -> dict:
        return {"success": True, "note": "Mock stripe webhook handled"}