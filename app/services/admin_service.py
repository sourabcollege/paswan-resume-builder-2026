from __future__ import annotations
from app.extensions import db
from app.models.user import User
from app.models.resume import Resume
from app.models.activity import ActivityLog
from app.models.job import Job
from app.models.subscription import Subscription


class AdminService:

    @staticmethod
    def get_all_users(
        page: int = 1,
        per_page: int = 20,
        search: str = "",
    ) -> dict:
        query = User.query
        if search:
            term = f"%{search}%"
            query = query.filter(
                db.or_(
                    User.username.ilike(term),
                    User.email.ilike(term),
                    User.full_name.ilike(term),
                )
            )
        pagination = query.order_by(
            User.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)

        return {
            "users": [
                {
                    "id": u.id,
                    "username": u.username,
                    "email": u.email,
                    "full_name": u.full_name,
                    "role": u.role,
                    "is_active": u.is_active,
                    "created_at": u.created_at.strftime("%d %b %Y"),
                }
                for u in pagination.items
            ],
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": page,
        }

    @staticmethod
    def get_user_detail(user_id: int) -> dict | None:
        user = User.query.get(user_id)
        if not user:
            return None
        resumes = Resume.query.filter_by(
            user_id=user_id, is_deleted=False
        ).count()
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "created_at": user.created_at.strftime("%d %b %Y"),
            "total_resumes": resumes,
        }

    @staticmethod
    def ban_user(user_id: int) -> dict:
        user = User.query.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        user.is_active = False
        db.session.commit()
        return {"success": True,
                "message": f"User {user.username} banned"}

    @staticmethod
    def unban_user(user_id: int) -> dict:
        user = User.query.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        user.is_active = True
        db.session.commit()
        return {"success": True,
                "message": f"User {user.username} unbanned"}

    @staticmethod
    def change_user_role(user_id: int, role: str) -> dict:
        user = User.query.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        user.role = role
        db.session.commit()
        return {"success": True,
                "message": f"Role changed to {role}"}

    @staticmethod
    def get_activity_logs(
        page: int = 1, action: str = ""
    ) -> dict:
        query = ActivityLog.query
        if action:
            query = query.filter_by(action=action)
        pagination = query.order_by(
            ActivityLog.created_at.desc()
        ).paginate(page=page, per_page=50, error_out=False)

        return {
            "logs": [
                {
                    "id": log.id,
                    "user_id": log.user_id,
                    "action": log.action,
                    "description": log.description,
                    "ip_address": log.ip_address,
                    "timestamp": log.created_at.strftime(
                        "%d %b %Y, %I:%M %p"
                    ),
                }
                for log in pagination.items
            ],
            "total": pagination.total,
            "pages": pagination.pages,
        }

    @staticmethod
    def get_system_stats() -> dict:
        total_users = User.query.count()
        active_users = User.query.filter_by(
            is_active=True
        ).count()
        total_resumes = Resume.query.filter_by(
            is_deleted=False
        ).count()
        total_jobs = Job.query.filter_by(is_active=True).count()
        pro_users = Subscription.query.filter_by(
            plan="pro", status="active"
        ).count()

        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_resumes": total_resumes,
            "total_jobs": total_jobs,
            "pro_subscribers": pro_users,
        }

    @staticmethod
    def create_job(data: dict) -> dict:
        required = ["title", "company", "description",
                    "required_skills"]
        for field in required:
            if not data.get(field):
                return {"success": False,
                        "error": f"{field} is required"}
        job = Job(
            title=data["title"],
            company=data["company"],
            description=data["description"],
            required_skills=data["required_skills"],
            location=data.get("location", ""),
            job_type=data.get("job_type", "full-time"),
            experience_level=data.get("experience_level", ""),
            is_active=True,
        )
        db.session.add(job)
        db.session.commit()
        return {"success": True, "job_id": job.id}

    @staticmethod
    def delete_job(job_id: int) -> dict:
        job = Job.query.get(job_id)
        if not job:
            return {"success": False, "error": "Job not found"}
        job.is_active = False
        db.session.commit()
        return {"success": True,
                "message": f"Job {job_id} deleted"}
    @staticmethod
    def delete_user(user_id: int) -> dict:
        user = User.query.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        db.session.delete(user)
        db.session.commit()
        return {"success": True, "message": f"User {user_id} deleted"}
