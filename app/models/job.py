from __future__ import annotations

import uuid

from app.extensions import db

from .base import JSONDict, JSONList, TimestampMixin, score_between_zero_and_hundred, utc_now


class Job(TimestampMixin, db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)

    title = db.Column(db.String(180), nullable=False)
    company_name = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(240), nullable=False)
    location = db.Column(db.String(180))
    workplace_type = db.Column(db.String(32), nullable=False, default="onsite")
    employment_type = db.Column(db.String(32), nullable=False, default="full_time")
    experience_level = db.Column(db.String(32), nullable=False, default="entry")
    status = db.Column(db.String(32), nullable=False, default="draft")
    visibility = db.Column(db.String(32), nullable=False, default="public")

    description = db.Column(db.Text, nullable=False)
    responsibilities = db.Column(db.Text)
    requirements_text = db.Column(db.Text, nullable=False)
    required_skills = db.Column(JSONList, nullable=False, default=list)
    preferred_skills = db.Column(JSONList, nullable=False, default=list)
    keywords = db.Column(JSONList, nullable=False, default=list)
    job_metadata = db.Column("job_metadata", JSONDict, nullable=False, default=dict)

    salary_min_cents = db.Column(db.Integer)
    salary_max_cents = db.Column(db.Integer)
    salary_currency = db.Column(db.String(3), nullable=False, default="INR")
    external_url = db.Column(db.String(2048))
    published_at = db.Column(db.DateTime(timezone=True))
    expires_at = db.Column(db.DateTime(timezone=True))

    created_by = db.relationship("User", back_populates="created_jobs", foreign_keys=[created_by_user_id])
    job_matches = db.relationship("JobMatch", back_populates="job", cascade="all, delete-orphan", lazy="selectin")
    analytics_history = db.relationship("AnalyticsHistory", back_populates="job", lazy="selectin")
    activity_logs = db.relationship("ActivityLog", back_populates="job", lazy="selectin")

    __table_args__ = (
        db.UniqueConstraint("company_name", "slug", name="uq_jobs_company_slug"),
        db.CheckConstraint("workplace_type IN ('onsite', 'remote', 'hybrid')", name="ck_jobs_workplace_type"),
        db.CheckConstraint(
            "employment_type IN ('full_time', 'part_time', 'contract', 'internship', 'freelance')",
            name="ck_jobs_employment_type",
        ),
        db.CheckConstraint(
            "experience_level IN ('entry', 'junior', 'mid', 'senior', 'lead', 'executive')",
            name="ck_jobs_experience_level",
        ),
        db.CheckConstraint("status IN ('draft', 'published', 'closed', 'archived')", name="ck_jobs_status"),
        db.CheckConstraint("visibility IN ('public', 'recruiter_only', 'private')", name="ck_jobs_visibility"),
        db.CheckConstraint(
            "salary_min_cents IS NULL OR salary_min_cents >= 0",
            name="ck_jobs_salary_min_non_negative",
        ),
        db.CheckConstraint(
            "salary_max_cents IS NULL OR salary_max_cents >= 0",
            name="ck_jobs_salary_max_non_negative",
        ),
        db.CheckConstraint(
            "salary_min_cents IS NULL OR salary_max_cents IS NULL OR salary_min_cents <= salary_max_cents",
            name="ck_jobs_salary_range_valid",
        ),
        db.Index("ix_jobs_status_published", "status", "published_at"),
        db.Index("ix_jobs_creator_status", "created_by_user_id", "status"),
        db.Index("ix_jobs_company_title", "company_name", "title"),
        db.Index("ix_jobs_experience_location", "experience_level", "location"),
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} company={self.company_name!r} title={self.title!r} status={self.status!r}>"


class JobMatch(TimestampMixin, db.Model):
    __tablename__ = "job_matches"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id = db.Column(db.Integer, nullable=False, index=True)
    version_id = db.Column(db.Integer, nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)

    match_score = db.Column(db.Float, nullable=False, default=0)
    skill_score = db.Column(db.Float, nullable=False, default=0)
    keyword_score = db.Column(db.Float, nullable=False, default=0)
    experience_score = db.Column(db.Float, nullable=False, default=0)
    education_score = db.Column(db.Float)
    status = db.Column(db.String(32), nullable=False, default="recommended")
    recommendation_rank = db.Column(db.Integer)

    matched_skills = db.Column(JSONList, nullable=False, default=list)
    missing_skills = db.Column(JSONList, nullable=False, default=list)
    priority_gaps = db.Column(JSONList, nullable=False, default=list)
    scoring_details = db.Column(JSONDict, nullable=False, default=dict)
    explanation = db.Column(db.Text)

    applied_at = db.Column(db.DateTime(timezone=True))
    shortlisted_at = db.Column(db.DateTime(timezone=True))
    rejected_at = db.Column(db.DateTime(timezone=True))
    last_calculated_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    user = db.relationship("User", back_populates="job_matches", foreign_keys=[user_id])
    resume = db.relationship("Resume", back_populates="job_matches")
    version = db.relationship("ResumeVersion", back_populates="job_matches")
    job = db.relationship("Job", back_populates="job_matches")

    __table_args__ = (
        db.ForeignKeyConstraint(
            ["resume_id", "user_id"],
            ["resumes.id", "resumes.user_id"],
            ondelete="CASCADE",
            name="fk_job_matches_resume_owner",
        ),
        db.ForeignKeyConstraint(
            ["version_id", "resume_id", "user_id"],
            ["resume_versions.id", "resume_versions.resume_id", "resume_versions.user_id"],
            ondelete="CASCADE",
            name="fk_job_matches_version_owner",
        ),
        db.UniqueConstraint("user_id", "resume_id", "version_id", "job_id", name="uq_job_matches_candidate_job"),
        db.CheckConstraint(
            "status IN ('recommended', 'saved', 'applied', 'shortlisted', 'rejected', 'hidden')",
            name="ck_job_matches_status",
        ),
        db.CheckConstraint(
            "recommendation_rank IS NULL OR recommendation_rank > 0",
            name="ck_job_matches_rank_positive",
        ),
        score_between_zero_and_hundred("match_score", "ck_job_matches_match_score_range"),
        score_between_zero_and_hundred("skill_score", "ck_job_matches_skill_score_range"),
        score_between_zero_and_hundred("keyword_score", "ck_job_matches_keyword_score_range"),
        score_between_zero_and_hundred("experience_score", "ck_job_matches_experience_score_range"),
        score_between_zero_and_hundred("education_score", "ck_job_matches_education_score_range"),
        db.Index("ix_job_matches_user_score", "user_id", "match_score"),
        db.Index("ix_job_matches_job_score", "job_id", "match_score"),
        db.Index("ix_job_matches_status_updated", "status", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<JobMatch id={self.id} user_id={self.user_id} job_id={self.job_id} score={self.match_score}>"
