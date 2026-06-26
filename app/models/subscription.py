from __future__ import annotations

from app.extensions import db

from .base import JSONDict, TimestampMixin


class Subscription(TimestampMixin, db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    plan_type = db.Column(db.String(32), nullable=False, default="free")
    status = db.Column(db.String(32), nullable=False, default="active")
    provider = db.Column(db.String(32), nullable=False, default="internal")
    provider_customer_id = db.Column(db.String(160), index=True)
    provider_subscription_id = db.Column(db.String(160), index=True)
    provider_price_id = db.Column(db.String(160))

    starts_at = db.Column(db.DateTime(timezone=True), nullable=False)
    current_period_start = db.Column(db.DateTime(timezone=True))
    current_period_end = db.Column(db.DateTime(timezone=True))
    trial_ends_at = db.Column(db.DateTime(timezone=True))
    canceled_at = db.Column(db.DateTime(timezone=True))
    cancel_at_period_end = db.Column(db.Boolean, nullable=False, default=False)

    resume_limit = db.Column(db.Integer, nullable=False, default=3)
    version_limit = db.Column(db.Integer, nullable=False, default=3)
    ai_enabled = db.Column(db.Boolean, nullable=False, default=False)
    recruiter_access = db.Column(db.Boolean, nullable=False, default=False)
    entitlements = db.Column(JSONDict, nullable=False, default=dict)

    user = db.relationship("User", back_populates="subscriptions", foreign_keys=[user_id])
    payments = db.relationship("Payment", back_populates="subscription", lazy="selectin")

    __table_args__ = (
        db.UniqueConstraint("id", "user_id", name="uq_subscriptions_id_user_id"),
        db.UniqueConstraint("provider", "provider_subscription_id", name="uq_subscriptions_provider_subscription"),
        db.CheckConstraint("plan_type IN ('free', 'pro', 'enterprise')", name="ck_subscriptions_plan_type"),
        db.CheckConstraint(
            "status IN ('active', 'trialing', 'past_due', 'canceled', 'expired', 'incomplete')",
            name="ck_subscriptions_status",
        ),
        db.CheckConstraint("provider IN ('internal', 'razorpay', 'stripe')", name="ck_subscriptions_provider"),
        db.CheckConstraint("resume_limit >= 0", name="ck_subscriptions_resume_limit_non_negative"),
        db.CheckConstraint("version_limit >= 0", name="ck_subscriptions_version_limit_non_negative"),
        db.CheckConstraint(
            "current_period_start IS NULL OR current_period_end IS NULL OR current_period_start <= current_period_end",
            name="ck_subscriptions_period_valid",
        ),
        db.Index("ix_subscriptions_user_status", "user_id", "status"),
        db.Index("ix_subscriptions_plan_status", "plan_type", "status"),
        db.Index("ix_subscriptions_provider_customer", "provider", "provider_customer_id"),
    )

    @property
    def is_paid_plan(self) -> bool:
        return self.plan_type in {"pro", "enterprise"}

    def __repr__(self) -> str:
        return f"<Subscription id={self.id} user_id={self.user_id} plan={self.plan_type!r} status={self.status!r}>"
