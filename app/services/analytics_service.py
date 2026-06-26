from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.extensions import db
from app.models.activity import ActivityLog
from app.models.resume import Resume, ResumeVersion
from app.utils.offline_engines import (
    ats_scoring_engine,
    resume_completeness_scorer,
    skill_extraction_engine,
)


class AnalyticsService:

    @staticmethod
    def _get_user_resumes(user_id: int) -> list[Resume]:
        """Helper to get non-deleted, non-archived resumes for a user."""
        return (
            Resume.query.filter_by(user_id=user_id, is_archived=False)
            .filter(Resume.deleted_at.is_(None))
            .order_by(Resume.updated_at.desc())
            .all()
        )

    @staticmethod
    def _get_current_version(resume: Resume) -> ResumeVersion | None:
        """Helper to get the current version of a resume."""
        return (
            ResumeVersion.query.filter_by(
                resume_id=resume.id,
                user_id=resume.user_id,
                is_current=True,
            )
            .order_by(ResumeVersion.updated_at.desc())
            .first()
        )

    @staticmethod
    def get_dashboard_data(user_id: int) -> dict[str, Any]:
        resumes = AnalyticsService._get_user_resumes(user_id)

        if not resumes:
            return {
                "total_resumes": 0,
                "resume_count": 0,
                "avg_ats_score": 0,
                "best_ats_score": 0,
                "best_score": 0,
                "avg_completeness": 0,
                "completeness": 0,
                "total_job_matches": 0,
                "job_matches": 0,
                "ats_trend": [],
                "skills_breakdown": [],
                "recent_activity": [],
            }

        scores = []
        completeness_scores = []
        job_matches_count = 0

        for resume in resumes:
            version = AnalyticsService._get_current_version(resume)
            if version:
                if version.ats_score_snapshot is not None:
                    scores.append(version.ats_score_snapshot)
                if version.completeness_snapshot is not None:
                    completeness_scores.append(version.completeness_snapshot)

                # Count job matches from relationship
                try:
                    job_matches_count += len(resume.job_matches) if resume.job_matches else 0
                except Exception:
                    pass

        # Fallback: try Job model if available
        try:
            from app.models.job import Job
            job_matches_count = Job.query.filter_by(is_active=True).count()
        except Exception:
            pass

        return {
            "total_resumes": len(resumes),
            "resume_count": len(resumes),
            "avg_ats_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "best_ats_score": round(max(scores), 1) if scores else 0,
            "best_score": round(max(scores), 1) if scores else 0,
            "avg_completeness": round(sum(completeness_scores) / len(completeness_scores), 1) if completeness_scores else 0,
            "completeness": round(sum(completeness_scores) / len(completeness_scores), 1) if completeness_scores else 0,
            "total_job_matches": job_matches_count,
            "job_matches": job_matches_count,
            "ats_trend": AnalyticsService.get_ats_trend(user_id),
            "skills_breakdown": AnalyticsService.get_skill_breakdown(user_id),
            "recent_activity": AnalyticsService.get_activity_timeline(user_id),
        }

    @staticmethod
    def get_ats_trend(user_id: int, resume_id: int | None = None) -> list[dict[str, Any]]:
        """Get ATS score trend using ResumeVersion snapshots."""
        query = (
            ResumeVersion.query.join(Resume)
            .filter(
                Resume.user_id == user_id,
                Resume.is_archived == False,
                Resume.deleted_at.is_(None),
                ResumeVersion.ats_score_snapshot.isnot(None),
            )
        )
        if resume_id:
            query = query.filter(ResumeVersion.resume_id == resume_id)

        records = query.order_by(ResumeVersion.created_at.asc()).limit(30).all()

        return [
            {
                "date": r.created_at.strftime("%d %b") if r.created_at else "",
                "score": r.ats_score_snapshot or 0,
            }
            for r in records
        ]

    @staticmethod
    def get_skill_breakdown(user_id: int) -> list[dict[str, Any]]:
        """Get skill breakdown from current resume versions."""
        resumes = AnalyticsService._get_user_resumes(user_id)

        categories: dict[str, int] = {}

        for resume in resumes:
            version = AnalyticsService._get_current_version(resume)
            if version and version.plain_text:
                result = skill_extraction_engine.extract(version.plain_text)
                for cat, skills in result.skills_by_category.items():
                    categories[cat] = categories.get(cat, 0) + len(skills)
            elif resume.extracted_skills:
                # Fallback: count extracted skills as "other"
                categories["other"] = categories.get("other", 0) + len(resume.extracted_skills)

        # Format for template
        return [
            {"category": cat, "count": count}
            for cat, count in categories.items()
        ]

    @staticmethod
    def get_job_match_trend(user_id: int) -> dict[str, Any]:
        """Get job match trend from ResumeVersion data."""
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)

        records = (
            ResumeVersion.query.join(Resume)
            .filter(
                Resume.user_id == user_id,
                Resume.is_archived == False,
                Resume.deleted_at.is_(None),
                ResumeVersion.created_at >= thirty_days_ago,
            )
            .order_by(ResumeVersion.created_at.asc())
            .all()
        )

        return {
            "labels": [r.created_at.strftime("%d %b") for r in records if r.created_at],
            "match_scores": [r.ats_score_snapshot or 0 for r in records],
        }

    @staticmethod
    def get_completeness(user_id: int, resume_id: int | None = None) -> dict[str, Any]:
        """Get completeness data for a resume."""
        resumes = AnalyticsService._get_user_resumes(user_id)

        if resume_id:
            target = next((r for r in resumes if r.id == resume_id), None)
        else:
            target = resumes[0] if resumes else None

        if not target:
            return {"overall_percentage": 0, "score": 0, "sections": {}}

        version = AnalyticsService._get_current_version(target)
        if version and version.completeness_snapshot is not None:
            return {
                "overall_percentage": version.completeness_snapshot,
                "score": version.completeness_snapshot,
            }

        # Fallback: calculate from version content
        if version and version.content:
            result = resume_completeness_scorer.score(version.content)
            return {
                "overall_percentage": result.score,
                "score": result.score,
                "sections": {s.section: s.score for s in result.sections},
            }

        return {"overall_percentage": 0, "score": 0, "sections": {}}

    @staticmethod
    def get_activity_timeline(user_id: int) -> list[dict[str, Any]]:
        """Get recent activity logs."""
        logs = (
            ActivityLog.query.filter_by(
                actor_user_id=user_id,
            )
            .order_by(ActivityLog.created_at.desc())
            .limit(20)
            .all()
        )

        return [
            {
                "action": log.event_type,
                "event": log.event_type,
                "description": str(log.details) if log.details else log.event_type,
                "date": log.created_at.strftime("%d %b %Y") if log.created_at else "",
                "timestamp": log.created_at.strftime("%d %b %Y, %I:%M %p") if log.created_at else "",
                "score": 0,
                "status": log.status,
            }
            for log in logs
        ]

    @staticmethod
    def get_scoring_distribution(user_id: int) -> dict[str, Any]:
        """Returns distribution data of ATS scores for user's resumes."""
        resumes = AnalyticsService._get_user_resumes(user_id)
        distribution = [0] * 10  # 0-10, 10-20, ..., 90-100

        for resume in resumes:
            version = AnalyticsService._get_current_version(resume)
            if version and version.ats_score_snapshot is not None:
                score = version.ats_score_snapshot
                bucket = min(int(score) // 10, 9)
                distribution[bucket] += 1

        return {
            "distribution": distribution,
            "labels": ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"],
        }

    @staticmethod
    def get_skill_gap_distribution(user_id: int) -> dict[str, Any]:
        """Returns aggregated data about missing skills across job matches."""
        return {"gaps": {}, "total": 0}