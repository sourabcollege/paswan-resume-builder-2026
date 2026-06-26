from __future__ import annotations
import os
from celery import Celery
from app.services.ai_service import AIService
from flask_mail import Message
from app.extensions import mail

# Initialize Celery
celery = Celery(__name__)
celery.conf.broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
celery.conf.result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")


@celery.task(name="tasks.ai_rewrite_resume")
def ai_rewrite_resume(user_id: int, resume_id: int):
    """Background task for AI resume rewrite."""
    return AIService.rewrite_resume(user_id, resume_id)


@celery.task(name="tasks.ai_improve_bullet")
def ai_improve_bullet(bullet: str):
    """Background task for AI bullet improvement."""
    return AIService.improve_bullet(bullet)


@celery.task(name="tasks.ai_generate_summary")
def ai_generate_summary(user_id: int, resume_id: int):
    """Background task for AI summary generation."""
    return AIService.generate_summary(user_id, resume_id)


@celery.task(name="tasks.ai_generate_cover_letter")
def ai_generate_cover_letter(user_id: int, resume_id: int, job_id: int):
    """Background task for AI cover letter generation."""
    return AIService.generate_cover_letter(user_id, resume_id, job_id)


@celery.task(name="tasks.generate_resume_pdf")
def generate_resume_pdf(resume_id: int, version_id: int):
    """Background task for PDF generation."""
    # In a real app, this would use a library like WeasyPrint or reportlab
    # For now, we simulate a long-running process
    import time
    time.sleep(2)
    return {"success": True, "path": f"/uploads/resumes/{resume_id}_{version_id}.pdf"}


@celery.task(name="tasks.send_email")
def send_email(subject: str, recipient: str, body: str):
    """Background task for sending emails."""
    msg = Message(subject, recipients=[recipient], body=body)
    try:
        mail.send(msg)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
