from __future__ import annotations

from app.payment import bp
from flask import jsonify, request, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.payment import bp
from app.services.payment_service import PaymentService


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
        return redirect(url_for("payments.get_plans"))
    return render_template("payment/checkout.html", plan=plan)


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
