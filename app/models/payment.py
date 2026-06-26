from __future__ import annotations

from app.extensions import db

from .base import JSONDict, TimestampMixin


class Payment(TimestampMixin, db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = db.Column(db.Integer, index=True)

    provider = db.Column(db.String(32), nullable=False)
    provider_payment_id = db.Column(db.String(160), index=True)
    provider_order_id = db.Column(db.String(160), index=True)
    provider_invoice_id = db.Column(db.String(160), index=True)
    checkout_session_id = db.Column(db.String(160), index=True)

    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    status = db.Column(db.String(32), nullable=False, default="created")
    failure_code = db.Column(db.String(80))
    failure_message = db.Column(db.String(500))
    receipt_number = db.Column(db.String(80), index=True)
    invoice_url = db.Column(db.String(2048))
    provider_payload = db.Column(JSONDict, nullable=False, default=dict)

    paid_at = db.Column(db.DateTime(timezone=True))
    refunded_at = db.Column(db.DateTime(timezone=True))

    user = db.relationship("User", back_populates="payments", foreign_keys=[user_id])
    subscription = db.relationship("Subscription", back_populates="payments")
    activity_logs = db.relationship("ActivityLog", back_populates="payment", lazy="selectin")

    __table_args__ = (
        db.ForeignKeyConstraint(
            ["subscription_id", "user_id"],
            ["subscriptions.id", "subscriptions.user_id"],
            name="fk_payments_subscription_owner",
        ),
        db.UniqueConstraint("provider", "provider_payment_id", name="uq_payments_provider_payment"),
        db.UniqueConstraint("provider", "provider_order_id", name="uq_payments_provider_order"),
        db.CheckConstraint("provider IN ('razorpay', 'stripe', 'internal')", name="ck_payments_provider"),
        db.CheckConstraint(
            "status IN ('created', 'pending', 'authorized', 'paid', 'failed', 'refunded', 'partially_refunded', 'canceled')",
            name="ck_payments_status",
        ),
        db.CheckConstraint("amount_cents >= 0", name="ck_payments_amount_non_negative"),
        db.Index("ix_payments_user_status", "user_id", "status"),
        db.Index("ix_payments_provider_status", "provider", "status"),
        db.Index("ix_payments_paid_at", "paid_at"),
    )

    def __repr__(self) -> str:
        return f"<Payment id={self.id} user_id={self.user_id} provider={self.provider!r} status={self.status!r}>"
