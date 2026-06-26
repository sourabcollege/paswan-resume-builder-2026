from __future__ import annotations
import os
import hmac
import hashlib
from datetime import datetime, timedelta
from app.extensions import db
from app.models.payment import Payment
from app.models.subscription import Subscription

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
        "price": 49900,
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
    def create_razorpay_order(
        user_id: int, plan: str
    ) -> dict:
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
            client = razorpay.Client(
                auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
            )
            order = client.order.create({
                "amount": amount,
                "currency": "INR",
                "payment_capture": 1,
                "notes": {
                    "user_id": str(user_id),
                    "plan": plan,
                },
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
        user_id: int,
        payment_id: str,
        order_id: str,
        signature: str,
    ) -> dict:
        if not RAZORPAY_KEY_SECRET:
            return PaymentService._activate_subscription(
                user_id, "pro", payment_id, order_id
            )

        body = f"{order_id}|{payment_id}"
        expected = hmac.new(
            RAZORPAY_KEY_SECRET.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()

        if hmac.compare_digest(expected, signature):
            plan = "pro"
            return PaymentService._activate_subscription(
                user_id, plan, payment_id, order_id
            )
        return {"success": False, "error": "Invalid signature"}

    @staticmethod
    def _activate_subscription(
        user_id: int,
        plan: str,
        payment_id: str,
        order_id: str,
    ) -> dict:
        existing = Subscription.query.filter_by(
            user_id=user_id
        ).first()

        if existing:
            existing.plan = plan
            existing.status = "active"
            existing.started_at = datetime.utcnow()
            existing.expires_at = datetime.utcnow() + timedelta(
                days=30
            )
        else:
            sub = Subscription(
                user_id=user_id,
                plan=plan,
                status="active",
                started_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=30),
            )
            db.session.add(sub)

        payment = Payment(
            user_id=user_id,
            razorpay_payment_id=payment_id,
            razorpay_order_id=order_id,
            amount=PLANS[plan]["price"],
            currency="INR",
            status="captured",
            plan=plan,
        )
        db.session.add(payment)
        db.session.commit()

        return {
            "success": True,
            "message": f"Subscription activated: {plan}",
            "plan": plan,
        }

    @staticmethod
    def handle_razorpay_webhook(
        payload: str, signature: str
    ) -> dict:
        if not RAZORPAY_KEY_SECRET:
            return {"success": True, "note": "Demo mode"}
        try:
            expected = hmac.new(
                RAZORPAY_KEY_SECRET.encode(),
                payload.encode(),
                hashlib.sha256,
            ).hexdigest()
            if hmac.compare_digest(expected, signature):
                return {"success": True}
            return {"success": False, "error": "Invalid signature"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_user_subscription(user_id: int) -> dict:
        sub = Subscription.query.filter_by(
            user_id=user_id
        ).first()
        if not sub:
            return {
                "plan": "free",
                "status": "active",
                "limits": PLANS["free"]["limits"],
            }
        return {
            "plan": sub.plan,
            "status": sub.status,
            "started_at": sub.started_at.strftime("%d %b %Y")
            if sub.started_at else None,
            "expires_at": sub.expires_at.strftime("%d %b %Y")
            if sub.expires_at else None,
            "limits": PLANS.get(sub.plan, PLANS["free"])["limits"],
        }

    @staticmethod
    def cancel_subscription(user_id: int) -> dict:
        sub = Subscription.query.filter_by(
            user_id=user_id
        ).first()
        if not sub:
            return {"success": False, "error": "No subscription"}
        sub.status = "cancelled"
        db.session.commit()
        return {
            "success": True,
            "message": "Subscription cancelled",
        }
    @staticmethod
    def create_stripe_session(user_id: int, plan: str) -> dict:
        return {"success": True, "session_id": "mock_stripe_session", "url": "/dashboard"}

    @staticmethod
    def verify_stripe_payment(user_id: int, session_id: str) -> dict:
        return PaymentService._activate_subscription(user_id, "pro", "stripe_pay_123", "stripe_ord_123")

    @staticmethod
    def handle_stripe_webhook(payload: str, signature: str) -> dict:
        return {"success": True, "note": "Mock stripe webhook handled"}
