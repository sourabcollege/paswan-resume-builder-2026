from __future__ import annotations

import uuid

from app.extensions import db

from .base import JSONDict, JSONList, TimestampMixin, score_between_zero_and_hundred


class Resume(TimestampMixin, db.Model):
    __tablename__ = "resumes"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    title = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(220), nullable=False)
    source_type = db.Column(db.String(32), nullable=False, default="builder")
    visibility = db.Column(db.String(32), nullable=False, default="private")
    public_slug = db.Column(db.String(220), unique=True)

    original_filename = db.Column(db.String(255))
    storage_path = db.Column(db.String(512))
    file_mime_type = db.Column(db.String(160))
    file_size_bytes = db.Column(db.Integer)
    checksum_sha256 = db.Column(db.String(64), index=True)

    parsing_status = db.Column(db.String(32), nullable=False, default="not_required")
    parsing_confidence = db.Column(db.Float)
    parsed_text_hash = db.Column(db.String(64), index=True)
    parsed_data = db.Column(JSONDict, nullable=False, default=dict)
    extracted_skills = db.Column(JSONList, nullable=False, default=list)

    is_archived = db.Column(db.Boolean, nullable=False, default=False)
    deleted_at = db.Column(db.DateTime(timezone=True))

    owner = db.relationship("User", back_populates="resumes", foreign_keys=[user_id])
    versions = db.relationship(
        "ResumeVersion",
        back_populates="resume",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    sections = db.relationship(
        "ResumeSection",
        back_populates="resume",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    scores = db.relationship("ResumeScore", back_populates="resume", cascade="all, delete-orphan", lazy="selectin")
    job_matches = db.relationship(
        "JobMatch",
        back_populates="resume",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    analytics_history = db.relationship(
        "AnalyticsHistory",
        back_populates="resume",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    # NOTE: ActivityLog intentionally does NOT cascade delete so audit trail survives resume deletion.
    activity_logs = db.relationship("ActivityLog", back_populates="resume", lazy="selectin")

    __table_args__ = (
        db.UniqueConstraint("id", "user_id", name="uq_resumes_id_user_id"),
        db.UniqueConstraint("user_id", "slug", name="uq_resumes_user_slug"),
        db.CheckConstraint("source_type IN ('builder', 'upload', 'import', 'api')", name="ck_resumes_source_type"),
        db.CheckConstraint(
            "visibility IN ('private', 'public', 'recruiter_visible')",
            name="ck_resumes_visibility",
        ),
        db.CheckConstraint(
            "parsing_status IN ('pending', 'parsed', 'failed', 'not_required')",
            name="ck_resumes_parsing_status",
        ),
        db.CheckConstraint("file_size_bytes IS NULL OR file_size_bytes >= 0", name="ck_resumes_file_size_non_negative"),
        score_between_zero_and_hundred("parsing_confidence", "ck_resumes_parsing_confidence_range"),
        db.Index("ix_resumes_user_created", "user_id", "created_at"),
        db.Index("ix_resumes_user_visibility", "user_id", "visibility", "is_archived"),
        db.Index("ix_resumes_parsing_status", "parsing_status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Resume id={self.id} user_id={self.user_id} title={self.title!r}>"


class ResumeVersion(TimestampMixin, db.Model):
    __tablename__ = "resume_versions"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id = db.Column(db.Integer, nullable=False, index=True)

    version_number = db.Column(db.Integer, nullable=False)
    label = db.Column(db.String(180), nullable=False, default="Untitled Version")
    status = db.Column(db.String(32), nullable=False, default="draft")
    template_key = db.Column(db.String(80), nullable=False, default="classic")
    content = db.Column(JSONDict, nullable=False, default=dict)
    plain_text = db.Column(db.Text)
    change_summary = db.Column(db.String(500))
    created_from_version_id = db.Column(db.Integer, db.ForeignKey("resume_versions.id", ondelete="SET NULL"))
    is_current = db.Column(db.Boolean, nullable=False, default=False)

    ats_score_snapshot = db.Column(db.Float)
    completeness_snapshot = db.Column(db.Float)

    owner = db.relationship("User", back_populates="resume_versions", foreign_keys=[user_id])
    resume = db.relationship("Resume", back_populates="versions")
    source_version = db.relationship("ResumeVersion", remote_side=[id], back_populates="derived_versions")
    derived_versions = db.relationship("ResumeVersion", back_populates="source_version", lazy="selectin")
    sections = db.relationship(
        "ResumeSection",
        back_populates="version",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    scores = db.relationship("ResumeScore", back_populates="version", cascade="all, delete-orphan", lazy="selectin")
    job_matches = db.relationship(
        "JobMatch",
        back_populates="version",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    analytics_history = db.relationship(
        "AnalyticsHistory",
        back_populates="version",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        db.ForeignKeyConstraint(
            ["resume_id", "user_id"],
            ["resumes.id", "resumes.user_id"],
            ondelete="CASCADE",
            name="fk_resume_versions_resume_owner",
        ),
        db.UniqueConstraint("id", "user_id", name="uq_resume_versions_id_user_id"),
        db.UniqueConstraint("id", "resume_id", "user_id", name="uq_resume_versions_id_resume_user"),
        db.UniqueConstraint("resume_id", "version_number", name="uq_resume_versions_resume_number"),
        db.CheckConstraint("version_number > 0", name="ck_resume_versions_version_number_positive"),
        db.CheckConstraint("status IN ('draft', 'active', 'archived')", name="ck_resume_versions_status"),
        score_between_zero_and_hundred("ats_score_snapshot", "ck_resume_versions_ats_snapshot_range"),
        score_between_zero_and_hundred("completeness_snapshot", "ck_resume_versions_completeness_range"),
        db.Index("ix_resume_versions_user_resume", "user_id", "resume_id", "created_at"),
        db.Index("ix_resume_versions_current", "resume_id", "is_current", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<ResumeVersion id={self.id} resume_id={self.resume_id} version={self.version_number}>"


class ResumeSection(TimestampMixin, db.Model):
    __tablename__ = "resume_sections"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id = db.Column(db.Integer, nullable=False, index=True)
    version_id = db.Column(db.Integer, nullable=False, index=True)

    section_type = db.Column(db.String(64), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    content = db.Column(JSONDict, nullable=False, default=dict)
    plain_text = db.Column(db.Text)
    extracted_keywords = db.Column(JSONList, nullable=False, default=list)
    source = db.Column(db.String(32), nullable=False, default="manual")
    confidence_score = db.Column(db.Float)

    owner = db.relationship("User", back_populates="resume_sections", foreign_keys=[user_id])
    resume = db.relationship("Resume", back_populates="sections")
    version = db.relationship("ResumeVersion", back_populates="sections")

    __table_args__ = (
        db.ForeignKeyConstraint(
            ["resume_id", "user_id"],
            ["resumes.id", "resumes.user_id"],
            ondelete="CASCADE",
            name="fk_resume_sections_resume_owner",
        ),
        db.ForeignKeyConstraint(
            ["version_id", "resume_id", "user_id"],
            ["resume_versions.id", "resume_versions.resume_id", "resume_versions.user_id"],
            ondelete="CASCADE",
            name="fk_resume_sections_version_owner",
        ),
        db.UniqueConstraint("version_id", "section_type", "sort_order", name="uq_resume_sections_version_type_order"),
        db.CheckConstraint("sort_order >= 0", name="ck_resume_sections_sort_order_non_negative"),
        db.CheckConstraint("source IN ('manual', 'parser', 'ai', 'import')", name="ck_resume_sections_source"),
        score_between_zero_and_hundred("confidence_score", "ck_resume_sections_confidence_range"),
        db.Index("ix_resume_sections_user_resume", "user_id", "resume_id", "section_type"),
        db.Index("ix_resume_sections_version_order", "version_id", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<ResumeSection id={self.id} version_id={self.version_id} type={self.section_type!r}>"