from __future__ import annotations

import uuid

from flask_login import UserMixin

from app.extensions import db

from .base import JSONDict, TimestampMixin, utc_now


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    ROLE_USER = "user"
    ROLE_RECRUITER = "recruiter"
    ROLE_ADMIN = "admin"

    STATUS_ACTIVE = "active"
    STATUS_PENDING = "pending_verification"
    STATUS_SUSPENDED = "suspended"
    STATUS_BANNED = "banned"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), nullable=False, default=ROLE_USER)
    account_status = db.Column(db.String(32), nullable=False, default=STATUS_PENDING)

    # ✅ Google OAuth field
    google_id = db.Column(db.String(120), unique=True, nullable=True, index=True)

    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(32))
    location = db.Column(db.String(160))
    headline = db.Column(db.String(180))
    bio = db.Column(db.Text)
    avatar_path = db.Column(db.String(512))
    profile_visibility = db.Column(db.String(32), nullable=False, default="private")
    profile_data = db.Column(JSONDict, nullable=False, default=dict)

    email_verified_at = db.Column(db.DateTime(timezone=True))
    last_login_at = db.Column(db.DateTime(timezone=True))
    last_seen_at = db.Column(db.DateTime(timezone=True))
    password_changed_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))
    weekly_summary_enabled = db.Column(db.Boolean, nullable=False, default=True)
    timezone = db.Column(db.String(64), nullable=False, default="Asia/Kolkata")
    locale = db.Column(db.String(16), nullable=False, default="en-IN")
    terms_accepted_at = db.Column(db.DateTime(timezone=True))
    privacy_consent_at = db.Column(db.DateTime(timezone=True))

    resumes = db.relationship("Resume", back_populates="owner", cascade="all, delete-orphan", lazy="selectin")
    resume_versions = db.relationship(
        "ResumeVersion",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    resume_sections = db.relationship(
        "ResumeSection",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    resume_scores = db.relationship(
        "ResumeScore",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    job_matches = db.relationship("JobMatch", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    analytics_history = db.relationship(
        "AnalyticsHistory",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    created_jobs = db.relationship(
        "Job",
        back_populates="created_by",
        foreign_keys="Job.created_by_user_id",
        lazy="selectin",
    )
    activity_logs_as_actor = db.relationship(
        "ActivityLog",
        back_populates="actor",
        foreign_keys="ActivityLog.actor_user_id",
        lazy="selectin",
    )
    activity_logs_as_target = db.relationship(
        "ActivityLog",
        back_populates="target_user",
        foreign_keys="ActivityLog.target_user_id",
        lazy="selectin",
    )
    subscriptions = db.relationship(
        "Subscription",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    payments = db.relationship("Payment", back_populates="user", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        db.CheckConstraint("role IN ('user', 'recruiter', 'admin')", name="ck_users_role"),
        db.CheckConstraint(
            "account_status IN ('active', 'pending_verification', 'suspended', 'banned')",
            name="ck_users_account_status",
        ),
        db.CheckConstraint(
            "profile_visibility IN ('private', 'public', 'recruiter_visible')",
            name="ck_users_profile_visibility",
        ),
        db.CheckConstraint("failed_login_count >= 0", name="ck_users_failed_login_count_non_negative"),
        db.Index("ix_users_role_status", "role", "account_status"),
        db.Index("ix_users_email_status", "email", "account_status"),
        db.Index("ix_users_created_role", "created_at", "role"),
    )

    @property
    def is_active(self) -> bool:
        return self.account_status == self.STATUS_ACTIVE

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    # ── NEW: Admin & Role Helpers ──
    @property
    def is_admin(self) -> bool:
        return self.role == self.ROLE_ADMIN

    @property
    def is_recruiter(self) -> bool:
        return self.role == self.ROLE_RECRUITER

    def has_role(self, role: str) -> bool:
        return self.role == role

    def can_be_admin(self, admin_email: str) -> bool:
        return self.email.lower().strip() == admin_email.lower().strip()

    # ── End New ──

    def set_password(self, password: str) -> None:
        import bcrypt

        password_bytes = password.encode("utf-8")
        self.password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")
        self.password_changed_at = utc_now()

    def check_password(self, password: str) -> bool:
        import bcrypt

        if not self.password_hash:
            return False
        return bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))

    def __repr__(self) -> str:
        return f"<User id={self.id} role={self.role!r} status={self.account_status!r}>"