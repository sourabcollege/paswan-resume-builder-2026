from __future__ import annotations

from app.extensions import db

from .base import JSONDict, JSONList, TimestampMixin, score_between_zero_and_hundred, utc_now


class ResumeScore(TimestampMixin, db.Model):
    __tablename__ = "resume_scores"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id = db.Column(db.Integer, nullable=False, index=True)
    version_id = db.Column(db.Integer, nullable=False, index=True)

    score_type = db.Column(db.String(32), nullable=False, default="ats")
    algorithm_version = db.Column(db.String(40), nullable=False, default="offline-v1")
    overall_score = db.Column(db.Float, nullable=False, default=0)
    keyword_score = db.Column(db.Float, nullable=False, default=0)
    formatting_score = db.Column(db.Float, nullable=False, default=0)
    experience_score = db.Column(db.Float, nullable=False, default=0)
    skills_score = db.Column(db.Float, nullable=False, default=0)
    education_score = db.Column(db.Float, nullable=False, default=0)
    completeness_score = db.Column(db.Float)

    suggestions = db.Column(JSONList, nullable=False, default=list)
    breakdown = db.Column(JSONDict, nullable=False, default=dict)
    raw_metrics = db.Column(JSONDict, nullable=False, default=dict)
    is_latest = db.Column(db.Boolean, nullable=False, default=True)
    calculated_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    user = db.relationship("User", back_populates="resume_scores", foreign_keys=[user_id])
    resume = db.relationship("Resume", back_populates="scores")
    version = db.relationship("ResumeVersion", back_populates="scores")

    __table_args__ = (
        db.ForeignKeyConstraint(
            ["resume_id", "user_id"],
            ["resumes.id", "resumes.user_id"],
            ondelete="CASCADE",
            name="fk_resume_scores_resume_owner",
        ),
        db.ForeignKeyConstraint(
            ["version_id", "resume_id", "user_id"],
            ["resume_versions.id", "resume_versions.resume_id", "resume_versions.user_id"],
            ondelete="CASCADE",
            name="fk_resume_scores_version_owner",
        ),
        db.CheckConstraint(
            "score_type IN ('ats', 'completeness', 'keyword_match', 'formatting')",
            name="ck_resume_scores_score_type",
        ),
        score_between_zero_and_hundred("overall_score", "ck_resume_scores_overall_range"),
        score_between_zero_and_hundred("keyword_score", "ck_resume_scores_keyword_range"),
        score_between_zero_and_hundred("formatting_score", "ck_resume_scores_formatting_range"),
        score_between_zero_and_hundred("experience_score", "ck_resume_scores_experience_range"),
        score_between_zero_and_hundred("skills_score", "ck_resume_scores_skills_range"),
        score_between_zero_and_hundred("education_score", "ck_resume_scores_education_range"),
        score_between_zero_and_hundred("completeness_score", "ck_resume_scores_completeness_range"),
        db.Index("ix_resume_scores_user_resume_latest", "user_id", "resume_id", "score_type", "is_latest"),
        db.Index("ix_resume_scores_version_calculated", "version_id", "calculated_at"),
    )

    def __repr__(self) -> str:
        return f"<ResumeScore id={self.id} resume_id={self.resume_id} type={self.score_type!r} score={self.overall_score}>"


class AnalyticsHistory(TimestampMixin, db.Model):
    __tablename__ = "analytics_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id = db.Column(db.Integer, index=True)
    version_id = db.Column(db.Integer, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id", ondelete="SET NULL"), index=True)

    metric_scope = db.Column(db.String(32), nullable=False, default="user")
    metric_name = db.Column(db.String(80), nullable=False)
    metric_value = db.Column(db.Float)
    dimension = db.Column(db.String(80))
    payload = db.Column(JSONDict, nullable=False, default=dict)
    period_start = db.Column(db.DateTime(timezone=True))
    period_end = db.Column(db.DateTime(timezone=True))
    recorded_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    user = db.relationship("User", back_populates="analytics_history", foreign_keys=[user_id])
    resume = db.relationship("Resume", back_populates="analytics_history")
    version = db.relationship("ResumeVersion", back_populates="analytics_history")
    job = db.relationship("Job", back_populates="analytics_history")

    __table_args__ = (
        db.ForeignKeyConstraint(
            ["resume_id", "user_id"],
            ["resumes.id", "resumes.user_id"],
            ondelete="CASCADE",
            name="fk_analytics_history_resume_owner",
        ),
        db.ForeignKeyConstraint(
            ["version_id", "resume_id", "user_id"],
            ["resume_versions.id", "resume_versions.resume_id", "resume_versions.user_id"],
            ondelete="CASCADE",
            name="fk_analytics_history_version_owner",
        ),
        db.CheckConstraint(
            "metric_scope IN ('user', 'resume', 'job', 'system')",
            name="ck_analytics_history_metric_scope",
        ),
        db.CheckConstraint(
            "metric_value IS NULL OR metric_value >= 0",
            name="ck_analytics_history_metric_value_non_negative",
        ),
        db.CheckConstraint(
            "period_start IS NULL OR period_end IS NULL OR period_start <= period_end",
            name="ck_analytics_history_period_valid",
        ),
        db.CheckConstraint("version_id IS NULL OR resume_id IS NOT NULL", name="ck_analytics_version_requires_resume"),
        db.Index("ix_analytics_user_metric_recorded", "user_id", "metric_name", "recorded_at"),
        db.Index("ix_analytics_resume_metric_recorded", "resume_id", "metric_name", "recorded_at"),
        db.Index("ix_analytics_job_metric_recorded", "job_id", "metric_name", "recorded_at"),
    )

    def __repr__(self) -> str:
        return f"<AnalyticsHistory id={self.id} user_id={self.user_id} metric={self.metric_name!r}>"
