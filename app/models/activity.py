from __future__ import annotations

import uuid

from app.extensions import db

from .base import JSONDict, TimestampMixin


class ActivityLog(TimestampMixin, db.Model):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    target_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resumes.id", ondelete="SET NULL"), index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id", ondelete="SET NULL"), index=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id", ondelete="SET NULL"), index=True)

    category = db.Column(db.String(40), nullable=False)
    event_type = db.Column(db.String(80), nullable=False)
    severity = db.Column(db.String(16), nullable=False, default="info")
    status = db.Column(db.String(32), nullable=False, default="success")
    object_type = db.Column(db.String(64))
    object_id = db.Column(db.String(64))
    request_id = db.Column(db.String(64), index=True)
    remote_addr_hash = db.Column(db.String(64))
    user_agent_hash = db.Column(db.String(64))
    details = db.Column(JSONDict, nullable=False, default=dict)

    actor = db.relationship(
        "User",
        back_populates="activity_logs_as_actor",
        foreign_keys=[actor_user_id],
    )
    target_user = db.relationship(
        "User",
        back_populates="activity_logs_as_target",
        foreign_keys=[target_user_id],
    )
    resume = db.relationship("Resume", back_populates="activity_logs")
    job = db.relationship("Job", back_populates="activity_logs")
    payment = db.relationship("Payment", back_populates="activity_logs")

    __table_args__ = (
        db.CheckConstraint(
            "category IN ('auth', 'resume', 'job', 'analytics', 'ai', 'payment', 'admin', 'security', 'system')",
            name="ck_activity_logs_category",
        ),
        db.CheckConstraint("severity IN ('debug', 'info', 'warning', 'error', 'critical')", name="ck_activity_logs_severity"),
        db.CheckConstraint("status IN ('success', 'failure', 'pending')", name="ck_activity_logs_status"),
        db.CheckConstraint(
            "resume_id IS NULL OR target_user_id IS NOT NULL",
            name="ck_activity_logs_resume_requires_target_user",
        ),
        db.Index("ix_activity_logs_actor_created", "actor_user_id", "created_at"),
        db.Index("ix_activity_logs_target_created", "target_user_id", "created_at"),
        db.Index("ix_activity_logs_category_created", "category", "created_at"),
        db.Index("ix_activity_logs_event_type_created", "event_type", "created_at"),
        db.Index("ix_activity_logs_security", "category", "severity", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ActivityLog id={self.id} category={self.category!r} event_type={self.event_type!r}>"
