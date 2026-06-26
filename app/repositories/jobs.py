from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_

from app.extensions import db
from app.models.job import Job, JobMatch


class JobRepository:
    def list_visible_for_user(
        self,
        user_id: int,
        role: str,
        *,
        search: str | None = None,
        location: str | None = None,
        experience_level: str | None = None,
        workplace_type: str | None = None,
        employment_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Job]:
        query = self._visible_query(user_id, role)
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Job.title.ilike(pattern),
                    Job.company_name.ilike(pattern),
                    Job.description.ilike(pattern),
                    Job.requirements_text.ilike(pattern),
                )
            )
        if location:
            query = query.filter(Job.location.ilike(f"%{location.strip()}%"))
        if experience_level:
            query = query.filter(Job.experience_level == experience_level)
        if workplace_type:
            query = query.filter(Job.workplace_type == workplace_type)
        if employment_type:
            query = query.filter(Job.employment_type == employment_type)
        return (
            query.order_by(Job.published_at.desc(), Job.created_at.desc())
            .offset(max(offset, 0))
            .limit(min(max(limit, 1), 250))
            .all()
        )

    def get_visible_by_public_id(self, public_id: str, user_id: int, role: str) -> Job | None:
        return self._visible_query(user_id, role).filter(Job.public_id == public_id).one_or_none()

    def get_match(
        self,
        user_id: int,
        job_id: int,
        resume_id: int,
        version_id: int,
    ) -> JobMatch | None:
        return JobMatch.query.filter_by(
            user_id=user_id,
            job_id=job_id,
            resume_id=resume_id,
            version_id=version_id,
        ).one_or_none()

    def list_matches_for_user(
        self,
        user_id: int,
        *,
        statuses: tuple[str, ...] | None = None,
    ) -> list[JobMatch]:
        query = JobMatch.query.filter_by(user_id=user_id)
        if statuses:
            query = query.filter(JobMatch.status.in_(statuses))
        return query.order_by(JobMatch.updated_at.desc(), JobMatch.match_score.desc()).all()

    def clear_recommendation_ranks(self, user_id: int, resume_id: int, version_id: int) -> None:
        JobMatch.query.filter_by(
            user_id=user_id,
            resume_id=resume_id,
            version_id=version_id,
        ).update({JobMatch.recommendation_rank: None}, synchronize_session="fetch")

    def add_match(self, match: JobMatch) -> JobMatch:
        db.session.add(match)
        return match

    def _visible_query(self, user_id: int, role: str):
        now = datetime.now(timezone.utc)
        visibility = [Job.visibility == "public"]
        if role in {"recruiter", "admin"}:
            visibility.append(Job.visibility == "recruiter_only")
        visibility.append(and_(Job.visibility == "private", Job.created_by_user_id == user_id))
        return Job.query.filter(
            Job.status == "published",
            or_(Job.expires_at.is_(None), Job.expires_at >= now),
            or_(*visibility),
        )
