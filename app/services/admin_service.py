from __future__ import annotations

import re
from datetime import datetime, timedelta
from sqlalchemy import func, desc
from app.extensions import db
from app.models.user import User
from app.models.resume import Resume
from app.models.job import Job
from app.models.activity import ActivityLog


class AdminService:
    """Admin operations with correct field mappings for Paswan Resume Builder schema."""

    # ===================== DASHBOARD STATS =====================

    @staticmethod
    def get_dashboard_stats() -> dict:
        """Return stats for admin dashboard. Keys match dashboard.html template."""
        try:
            total_users = User.query.count()
            total_resumes = Resume.query.count()
            total_jobs = Job.query.count()

            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            active_users_30d = User.query.filter(
                User.last_login_at >= thirty_days_ago
            ).count()

            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            new_users_today = User.query.filter(User.created_at >= today).count()

            # Keys expected by dashboard.html
            return {
                "total_users": total_users,
                "premium_users": 0,  # TODO: hook to Subscription if needed
                "recruiters": User.query.filter_by(role=User.ROLE_RECRUITER).count(),
                "resumes_uploaded": total_resumes,
                "jobs_posted": Job.query.filter_by(status="published").count(),
                "payments_total": 0,  # TODO: hook to Payment if needed
                "today_signups": new_users_today,
                # Extra keys for other templates
                "active_users": active_users_30d,
                "new_resumes_today": Resume.query.filter(Resume.created_at >= today).count(),
                "banned_accounts": User.query.filter_by(account_status=User.STATUS_BANNED).count(),
                "pending_accounts": User.query.filter_by(account_status=User.STATUS_PENDING).count(),
                "admin_count": User.query.filter_by(role=User.ROLE_ADMIN).count(),
                "user_count": User.query.filter_by(role=User.ROLE_USER).count(),
                "recent_activity": AdminService._get_recent_activity(),
            }
        except Exception as e:
            return {
                "total_users": 0, "premium_users": 0, "recruiters": 0,
                "resumes_uploaded": 0, "jobs_posted": 0, "payments_total": 0,
                "today_signups": 0, "active_users": 0, "new_resumes_today": 0,
                "banned_accounts": 0, "pending_accounts": 0,
                "admin_count": 0, "user_count": 0,
                "recent_activity": [], "error": str(e),
            }

    # ===================== USER MANAGEMENT =====================

    @staticmethod
    def get_all_users(
        page: int = 1,
        per_page: int = 20,
        search: str = "",
        role: str | None = None,
        status: str | None = None,
    ) -> dict:
        query = User.query
        if search:
            term = f"%{search}%"
            query = query.filter(
                db.or_(
                    User.email.ilike(term),
                    User.first_name.ilike(term),
                    User.last_name.ilike(term),
                )
            )
        if role:
            query = query.filter_by(role=role)
        if status:
            query = query.filter_by(account_status=status)

        pagination = query.order_by(desc(User.created_at)).paginate(
            page=page, per_page=per_page, error_out=False
        )

        return {
            "users": [
                {
                    "id": u.id,
                    "email": u.email,
                    "first_name": u.first_name,
                    "last_name": u.last_name,
                    "role": u.role,
                    "account_status": u.account_status,
                    "is_active": u.is_active,
                    "is_email_verified": u.is_email_verified,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                    "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                }
                for u in pagination.items
            ],
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": page,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
        }

    @staticmethod
    def get_user_detail(user_id: int) -> dict | None:
        user = User.query.get(user_id)
        if not user:
            return None
        resume_count = Resume.query.filter_by(user_id=user_id).count()
        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "account_status": user.account_status,
            "is_active": user.is_active,
            "is_email_verified": user.is_email_verified,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "total_resumes": resume_count,
        }

    @staticmethod
    def ban_user(user_id: int, admin_user=None) -> dict:
        user = User.query.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        if user.role == User.ROLE_ADMIN:
            return {"success": False, "error": "Cannot ban admin users"}
        user.account_status = User.STATUS_BANNED
        db.session.commit()
        AdminService._log_activity(
            actor_user_id=admin_user.id if admin_user else None,
            target_user_id=user.id,
            category="admin",
            event_type="ban_user",
            severity="warning",
            status="success",
            object_type="user",
            object_id=str(user_id),
            details={"admin_email": admin_user.email if admin_user else None},
        )
        return {"success": True, "message": f"User {user.email} has been banned"}

    @staticmethod
    def unban_user(user_id: int, admin_user=None) -> dict:
        user = User.query.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        user.account_status = User.STATUS_ACTIVE
        db.session.commit()
        AdminService._log_activity(
            actor_user_id=admin_user.id if admin_user else None,
            target_user_id=user.id,
            category="admin",
            event_type="unban_user",
            severity="info",
            status="success",
            object_type="user",
            object_id=str(user_id),
            details={"admin_email": admin_user.email if admin_user else None},
        )
        return {"success": True, "message": f"User {user.email} has been unbanned"}

    @staticmethod
    def change_user_role(user_id: int, role: str, admin_user=None) -> dict:
        user = User.query.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        if role not in (User.ROLE_USER, User.ROLE_RECRUITER, User.ROLE_ADMIN):
            return {"success": False, "error": "Invalid role"}
        user.role = role
        db.session.commit()
        AdminService._log_activity(
            actor_user_id=admin_user.id if admin_user else None,
            target_user_id=user.id,
            category="admin",
            event_type="change_role",
            severity="info",
            status="success",
            object_type="user",
            object_id=str(user_id),
            details={"new_role": role, "admin_email": admin_user.email if admin_user else None},
        )
        return {"success": True, "message": f"Role changed to {role}"}

    @staticmethod
    def delete_user(user_id: int, admin_user=None) -> dict:
        user = User.query.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        if user.role == User.ROLE_ADMIN:
            return {"success": False, "error": "Cannot delete admin users"}
        user_email = user.email
        db.session.delete(user)
        db.session.commit()
        AdminService._log_activity(
            actor_user_id=admin_user.id if admin_user else None,
            category="admin",
            event_type="delete_user",
            severity="warning",
            status="success",
            object_type="user",
            object_id=str(user_id),
            details={"deleted_user_email": user_email, "admin_email": admin_user.email if admin_user else None},
        )
        return {"success": True, "message": f"User {user_email} deleted permanently"}

    # ===================== RESUME MANAGEMENT =====================

    @staticmethod
    def get_all_resumes(
        page: int = 1, per_page: int = 20, search: str | None = None
    ) -> dict:
        query = Resume.query.join(User)
        if search:
            term = f"%{search}%"
            query = query.filter(
                db.or_(
                    Resume.title.ilike(term),
                    User.email.ilike(term),
                )
            )
        pagination = query.order_by(desc(Resume.created_at)).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return {
            "resumes": [
                {
                    "id": r.id,
                    "title": r.title,
                    "user_id": r.user_id,
                    "user_email": r.owner.email if r.owner else "Unknown",
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in pagination.items
            ],
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": page,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
        }

    @staticmethod
    def delete_resume(resume_id: int, admin_user=None) -> dict:
        resume = Resume.query.get(resume_id)
        if not resume:
            return {"success": False, "error": "Resume not found"}
        title = resume.title
        db.session.delete(resume)
        db.session.commit()
        AdminService._log_activity(
            actor_user_id=admin_user.id if admin_user else None,
            target_user_id=resume.user_id,
            category="admin",
            event_type="delete_resume",
            severity="warning",
            status="success",
            object_type="resume",
            object_id=str(resume_id),
            details={"resume_title": title, "admin_email": admin_user.email if admin_user else None},
        )
        return {"success": True, "message": f"Resume '{title}' deleted"}

    # ===================== JOB MANAGEMENT =====================

    @staticmethod
    def get_all_jobs(
        page: int = 1, per_page: int = 20, search: str | None = None
    ) -> dict:
        query = Job.query
        if search:
            term = f"%{search}%"
            query = query.filter(
                db.or_(
                    Job.title.ilike(term),
                    Job.company_name.ilike(term),
                    Job.location.ilike(term),
                )
            )
        pagination = query.order_by(desc(Job.created_at)).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return {
            "jobs": [
                {
                    "id": j.id,
                    "title": j.title,
                    "company": j.company_name,
                    "location": j.location or "Remote",
                    "status": j.status,
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                }
                for j in pagination.items
            ],
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": page,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
        }

    @staticmethod
    def create_job(data: dict) -> dict:
        required = ["title", "company_name", "description", "required_skills"]
        for field in required:
            if not data.get(field):
                return {"success": False, "error": f"{field} is required"}

        raw_slug = f"{data['company_name']}-{data['title']}"
        slug = re.sub(r"[^\w]+", "-", raw_slug.lower()).strip("-")

        job = Job(
            title=data["title"],
            company_name=data["company_name"],
            slug=slug,
            description=data["description"],
            required_skills=data["required_skills"],
            location=data.get("location", ""),
            workplace_type=data.get("workplace_type", "onsite"),
            employment_type=data.get("employment_type", "full_time"),
            experience_level=data.get("experience_level", "entry"),
            status="published",
            visibility="public",
        )
        db.session.add(job)
        db.session.commit()
        return {"success": True, "job_id": job.id}

    @staticmethod
    def delete_job(job_id: int, admin_user=None) -> dict:
        job = Job.query.get(job_id)
        if not job:
            return {"success": False, "error": "Job not found"}
        title = job.title
        db.session.delete(job)
        db.session.commit()
        AdminService._log_activity(
            actor_user_id=admin_user.id if admin_user else None,
            category="admin",
            event_type="delete_job",
            severity="warning",
            status="success",
            object_type="job",
            object_id=str(job_id),
            details={"job_title": title, "admin_email": admin_user.email if admin_user else None},
        )
        return {"success": True, "message": f"Job '{title}' deleted"}

    # ===================== ACTIVITY LOGS =====================

    @staticmethod
    def get_activity_logs(
        page: int = 1,
        action: str = "",
        per_page: int = 50,
        entity_type: str | None = None,
        user_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict:
        query = ActivityLog.query
        if action:
            query = query.filter_by(event_type=action)
        if entity_type:
            query = query.filter_by(object_type=entity_type)
        if user_id:
            query = query.filter_by(actor_user_id=user_id)
        if date_from:
            query = query.filter(ActivityLog.created_at >= date_from)
        if date_to:
            query = query.filter(ActivityLog.created_at <= date_to)

        pagination = query.order_by(desc(ActivityLog.created_at)).paginate(
            page=page, per_page=per_page, error_out=False
        )

        return {
            "logs": [
                {
                    "id": log.id,
                    "event_id": log.event_id,
                    "actor_user_id": log.actor_user_id,
                    "target_user_id": log.target_user_id,
                    "user_email": log.actor.email if log.actor else "System",
                    "user_role": log.actor.role if log.actor else "system",
                    "category": log.category,
                    "action": log.event_type,
                    "entity_type": log.object_type,
                    "entity_id": log.object_id,
                    "description": log.details.get("description") if log.details else None,
                    "status": log.status,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in pagination.items
            ],
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": page,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
        }

    @staticmethod
    def get_log_actions() -> list:
        actions = db.session.query(ActivityLog.event_type).distinct().all()
        return [a[0] for a in actions if a[0]]

    # ===================== SYSTEM STATS =====================

    @staticmethod
    def get_system_stats() -> dict:
        return {
            "total_users": User.query.count(),
            "active_users": User.query.filter_by(account_status=User.STATUS_ACTIVE).count(),
            "total_resumes": Resume.query.count(),
            "total_jobs": Job.query.filter_by(status="published").count(),
        }

    # ===================== INTERNAL HELPERS =====================

    @staticmethod
    def _get_recent_activity() -> list:
        logs = ActivityLog.query.order_by(desc(ActivityLog.created_at)).limit(10).all()
        return [
            {
                "id": log.id,
                "action": log.event_type,
                "user_email": log.actor.email if log.actor else "System",
                "status": log.status,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]

    @staticmethod
    def _log_activity(
        actor_user_id=None,
        target_user_id=None,
        category="system",
        event_type="unknown",
        severity="info",
        status="success",
        object_type=None,
        object_id=None,
        details=None,
    ):
        try:
            log = ActivityLog(
                actor_user_id=actor_user_id,
                target_user_id=target_user_id,
                category=category,
                event_type=event_type,
                severity=severity,
                status=status,
                object_type=object_type,
                object_id=object_id,
                details=details or {},
            )
            db.session.add(log)
            db.session.commit()
            return log
        except Exception:
            db.session.rollback()
            return None