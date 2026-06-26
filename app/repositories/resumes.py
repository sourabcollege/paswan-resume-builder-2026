from __future__ import annotations

from app.extensions import db
from app.models.analytics import ResumeScore
from app.models.resume import Resume, ResumeSection, ResumeVersion


class ResumeRepository:
    def list_for_user(self, user_id: int, *, include_archived: bool = False) -> list[Resume]:
        query = Resume.query.filter_by(user_id=user_id).filter(Resume.deleted_at.is_(None))
        if not include_archived:
            query = query.filter_by(is_archived=False)
        return query.order_by(Resume.updated_at.desc()).all()

    def get_by_public_id_for_user(self, public_id: str, user_id: int) -> Resume | None:
        return (
            Resume.query.filter_by(public_id=public_id, user_id=user_id, is_archived=False)
            .filter(Resume.deleted_at.is_(None))
            .one_or_none()
        )

    def get_by_public_id(self, public_id: str) -> Resume | None:
        return Resume.query.filter_by(public_id=public_id).filter(Resume.deleted_at.is_(None)).one_or_none()

    def get_by_id_for_user(self, resume_id: int, user_id: int) -> Resume | None:
        return (
            Resume.query.filter_by(id=resume_id, user_id=user_id, is_archived=False)
            .filter(Resume.deleted_at.is_(None))
            .one_or_none()
        )

    def get_by_id(self, resume_id: int) -> Resume | None:
        return Resume.query.filter_by(id=resume_id).filter(Resume.deleted_at.is_(None)).one_or_none()

    def count_for_user(self, user_id: int) -> int:
        return (
            Resume.query.filter_by(user_id=user_id, is_archived=False)
            .filter(Resume.deleted_at.is_(None))
            .count()
        )

    def get_version_by_public_id_for_user(self, public_id: str, user_id: int) -> ResumeVersion | None:
        return ResumeVersion.query.filter_by(public_id=public_id, user_id=user_id).one_or_none()

    def get_current_version(self, resume_id: int, user_id: int) -> ResumeVersion | None:
        return (
            ResumeVersion.query.filter_by(resume_id=resume_id, user_id=user_id, is_current=True)
            .order_by(ResumeVersion.updated_at.desc())
            .first()
        )

    def list_versions(self, resume_id: int, user_id: int) -> list[ResumeVersion]:
        return (
            ResumeVersion.query.filter_by(resume_id=resume_id, user_id=user_id)
            .order_by(ResumeVersion.version_number.desc())
            .all()
        )

    def list_sections(self, version_id: int, user_id: int) -> list[ResumeSection]:
        return (
            ResumeSection.query.filter_by(version_id=version_id, user_id=user_id)
            .order_by(ResumeSection.sort_order.asc(), ResumeSection.id.asc())
            .all()
        )

    def replace_sections(
        self,
        version_id: int,
        resume_id: int,
        user_id: int,
        sections: list[ResumeSection],
    ) -> None:
        ResumeSection.query.filter_by(
            version_id=version_id,
            resume_id=resume_id,
            user_id=user_id,
        ).delete(synchronize_session="fetch")
        db.session.add_all(sections)

    def next_version_number(self, resume_id: int) -> int:
        latest = (
            db.session.query(db.func.max(ResumeVersion.version_number))
            .filter(ResumeVersion.resume_id == resume_id)
            .scalar()
        )
        return int(latest or 0) + 1

    def slug_exists(self, user_id: int, slug: str) -> bool:
        return db.session.query(Resume.id).filter_by(user_id=user_id, slug=slug).first() is not None

    def add(self, instance):
        db.session.add(instance)
        return instance

    def flush(self) -> None:
        db.session.flush()

    def commit(self) -> None:
        db.session.commit()

    def rollback(self) -> None:
        db.session.rollback()

    def delete(self, resume: Resume) -> None:
        """Hard delete a resume and all cascaded relationships."""
        db.session.delete(resume)
        db.session.commit()

    def set_current_version(self, resume_id: int, user_id: int, version: ResumeVersion) -> None:
        ResumeVersion.query.filter_by(resume_id=resume_id, user_id=user_id, is_current=True).update(
            {"is_current": False, "status": "archived"},
            synchronize_session=False,
        )
        version.is_current = True
        version.status = "active"

    def mark_scores_not_latest(self, resume_id: int, user_id: int, score_type: str = "ats") -> None:
        ResumeScore.query.filter_by(
            resume_id=resume_id,
            user_id=user_id,
            score_type=score_type,
            is_latest=True,
        ).update({ResumeScore.is_latest: False}, synchronize_session="fetch")

    def get_latest_score_for_version(
        self,
        version_id: int,
        user_id: int,
        score_type: str = "ats",
    ) -> ResumeScore | None:
        return (
            ResumeScore.query.filter_by(
                version_id=version_id,
                user_id=user_id,
                score_type=score_type,
                is_latest=True,
            )
            .order_by(ResumeScore.calculated_at.desc())
            .first()
        )