from __future__ import annotations

import io
import qrcode
import base64

from app.payment import bp
from flask import jsonify, request, render_template, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.services.payment_service import PaymentService


# UPI ID for static QR payments
UPI_ID = "9975322192@pthdfc"


def _generate_upi_qr(amount: int, plan: str) -> str:
    """Generate a UPI payment QR code as base64 data URI."""
    upi_url = (
        f"upi://pay?pa={UPI_ID}"
        f"&pn=PaswanResume"
        f"&am={amount}"
        f"&cu=INR"
        f"&tn=Subscribe+to+{plan}+plan"
    )

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(upi_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_base64 = base64.b64encode(buffer.getvalue()).decode()

    return f"data:image/png;base64,{img_base64}"


@bp.route("/plans", methods=["GET"])
def get_plans():
    plans = PaymentService.get_plans()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("format") == "json":
        return jsonify(plans), 200
    return render_template("payment/plans.html", plans=plans["plans"])


@bp.route("/checkout", methods=["GET"])
@login_required
def checkout():
    plan = request.args.get("plan", "pro")
    if plan not in ("pro", "enterprise"):
        return redirect(url_for("payment.get_plans"))

    plan_data = PaymentService.get_plans()["plans"].get(plan, {})
    amount_paise = plan_data.get("price", 0)
    amount_rupees = amount_paise // 100

    qr_data_uri = _generate_upi_qr(amount_rupees, plan)

    return render_template(
        "payment/checkout.html",
        plan=plan,
        amount=amount_rupees,
        upi_id=UPI_ID,
        qr_code=qr_data_uri,
    )


@bp.route("/create-order", methods=["POST"])
@login_required
def create_order():
    data = request.get_json()
    plan = data.get("plan", "")
    provider = data.get("provider", "razorpay")

    if plan not in ("pro", "enterprise"):
        return jsonify({"error": "Invalid plan"}), 400

    if provider == "stripe":
        result = PaymentService.create_stripe_session(
            user_id=current_user.id,
            plan=plan,
        )
    else:
        result = PaymentService.create_razorpay_order(
            user_id=current_user.id,
            plan=plan,
        )
    return jsonify(result), 200


@bp.route("/verify", methods=["POST"])
@login_required
def verify_payment():
    data = request.get_json()
    provider = data.get("provider", "razorpay")

    if provider == "stripe":
        result = PaymentService.verify_stripe_payment(
            user_id=current_user.id,
            session_id=data.get("session_id", ""),
        )
    else:
        result = PaymentService.verify_razorpay_payment(
            user_id=current_user.id,
            payment_id=data.get("razorpay_payment_id", ""),
            order_id=data.get("razorpay_order_id", ""),
            signature=data.get("razorpay_signature", ""),
        )
    return jsonify(result), 200


# ═══════════════════════════════════════════════════════════
# 🆕 NEW: Generic Payment Webhook — Logs only, NO auto-activation
# ═══════════════════════════════════════════════════════════
@bp.route("/webhook", methods=["POST"])
def payment_webhook():
    """
    Generic payment webhook for Paytm / UPI / any provider.
    Logs the payment but does NOT auto-activate subscription.
    Admin must manually verify and activate.
    """
    data = request.get_json() or {}

    # Optional: verify webhook secret from header
    secret = request.headers.get("X-Webhook-Secret", "")
    expected = current_app.config.get("PAYMENT_WEBHOOK_SECRET", "")
    if expected and secret != expected:
        return jsonify({"success": False, "error": "Invalid webhook secret"}), 401

    result = PaymentService.handle_payment_webhook(data)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@bp.route("/webhook/razorpay", methods=["POST"])
def razorpay_webhook():
    payload = request.get_data(as_text=True)
    signature = request.headers.get("X-Razorpay-Signature", "")
    result = PaymentService.handle_razorpay_webhook(
        payload=payload,
        signature=signature,
    )
    return jsonify(result), 200


@bp.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    signature = request.headers.get("Stripe-Signature", "")
    result = PaymentService.handle_stripe_webhook(
        payload=payload,
        signature=signature,
    )
    return jsonify(result), 200


@bp.route("/subscription", methods=["GET"])
@login_required
def get_subscription():
    result = PaymentService.get_user_subscription(current_user.id)
    return jsonify(result), 200


@bp.route("/cancel", methods=["POST"])
@login_required
def cancel_subscription():
    result = PaymentService.cancel_subscription(current_user.id)
    return jsonify(result), 200