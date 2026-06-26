from __future__ import annotations
from app.models.user import User
from app.models.resume import Resume
from app.utils.offline_engines import ATSScoringEngine


class RecruiterService:

    @staticmethod
    def search_candidates(
        skills: str = "",
        min_ats: int = 0,
        max_ats: int = 100,
        experience: str = "",
    ) -> dict:
        users = User.query.filter_by(
            role="user", is_active=True
        ).all()

        results = []
        skill_list = [s.strip().lower() for s in skills.split(",")
                      if s.strip()] if skills else []

        for user in users:
            resumes = Resume.query.filter_by(
                user_id=user.id, is_deleted=False
            ).all()

            if not resumes:
                continue

            best_resume = None
            best_score = 0

            for resume in resumes:
                if resume.parsed_content:
                    score = ATSScoringEngine().score(
                        resume.parsed_content
                    ).get("total_score", 0)
                    if score > best_score:
                        best_score = score
                        best_resume = resume

            if best_resume is None:
                continue

            if not (min_ats <= best_score <= max_ats):
                continue

            content = best_resume.parsed_content or {}
            candidate_skills = [
                s.lower() for s in content.get("skills", [])
            ]

            if skill_list:
                matched = [s for s in skill_list
                           if s in candidate_skills]
                if not matched:
                    continue
                skill_match = round(
                    len(matched) / len(skill_list) * 100, 1
                )
            else:
                skill_match = 100.0

            results.append({
                "user_id": user.id,
                "name": user.full_name or user.username,
                "email": user.email,
                "ats_score": best_score,
                "skill_match": skill_match,
                "skills": content.get("skills", [])[:10],
                "resume_id": best_resume.id,
            })

        results.sort(key=lambda x: x["ats_score"], reverse=True)
        return {"candidates": results, "total": len(results)}

    @staticmethod
    def get_candidate_profile(user_id: int) -> dict | None:
        user = User.query.filter_by(
            id=user_id, role="user", is_active=True
        ).first()
        if not user:
            return None

        resumes = Resume.query.filter_by(
            user_id=user_id, is_deleted=False
        ).all()

        resume_list = []
        for resume in resumes:
            content = resume.parsed_content or {}
            score = 0
            if content:
                score = ATSScoringEngine().score(
                    content
                ).get("total_score", 0)
            resume_list.append({
                "resume_id": resume.id,
                "title": resume.title,
                "ats_score": score,
                "skills": content.get("skills", []),
                "created_at": resume.created_at.strftime(
                    "%d %b %Y"
                ),
            })

        return {
            "user_id": user.id,
            "name": user.full_name or user.username,
            "email": user.email,
            "resumes": resume_list,
        }

    @staticmethod
    def shortlist_candidate(
        recruiter_id: int,
        candidate_id: int,
        note: str = "",
    ) -> dict:
        return {
            "success": True,
            "message": f"Candidate {candidate_id} shortlisted",
            "note": note,
        }

    @staticmethod
    def get_shortlist(recruiter_id: int) -> dict:
        return {"shortlist": [], "total": 0}

    @staticmethod
    def remove_shortlist(
        recruiter_id: int, candidate_id: int
    ) -> dict:
        return {
            "success": True,
            "message": f"Candidate {candidate_id} removed",
        }

    @staticmethod
    def get_resume_download_url(user_id: int) -> dict | None:
        resume = Resume.query.filter_by(
            user_id=user_id, is_deleted=False
        ).first()
        if not resume:
            return None
        return {
            "resume_id": resume.id,
            "download_url": f"/resume/download/{resume.id}",
        }
