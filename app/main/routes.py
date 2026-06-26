from typing import Any

from flask import render_template, current_app, jsonify, request, url_for, redirect
from flask_login import login_required, current_user
from sqlalchemy import text, or_
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from flask_limiter.errors import RateLimitExceeded
from jinja2 import TemplateNotFound

from app.extensions import db, limiter
from app.logging_config import get_security_logger
from app.models.activity import ActivityLog
from app.models.analytics import ResumeScore
from app.repositories.resumes import ResumeRepository
from app.services.job_service import JobService

from app.main import bp


@bp.get("/")
def index():
    from flask_login import current_user
    return render_template("index.html", current_user=current_user)


@bp.get("/dashboard")
@login_required
def dashboard():
    user_id = current_user.id
    resumes = ResumeRepository().list_for_user(user_id)
    latest_score = (
        ResumeScore.query.filter_by(user_id=user_id, score_type="ats", is_latest=True)
        .order_by(ResumeScore.calculated_at.desc())
        .first()
    )
    recent_activity = (
        ActivityLog.query.filter(
            or_(
                ActivityLog.actor_user_id == user_id,
                ActivityLog.target_user_id == user_id,
            )
        )
        .order_by(ActivityLog.created_at.desc())
        .limit(8)
        .all()
    )
    recommendations_result = JobService().preview_top_recommendations(current_user._get_current_object())
    return render_template(
        "dashboard.html",
        resume_count=len(resumes),
        latest_ats_score=latest_score.overall_score if latest_score else None,
        recent_activity=recent_activity,
        resumes=resumes[:5],
        recommendations=recommendations_result.data.get("recommendations", []),
        resume_context=recommendations_result.data.get("resume_context"),
    )


@bp.get("/health")
def health():
    status_code = 200
    checks: dict[str, str] = {"application": "ok"}

    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except SQLAlchemyError:
        db.session.rollback()
        checks["database"] = "unavailable"
        status_code = 503
        current_app.logger.exception(
            "database_health_check_failed",
            extra={"event": "database_health_check_failed"},
        )

    payload: dict[str, Any] = {
        "status": "ok" if status_code == 200 else "degraded",
        "service": current_app.config["APP_NAME"],
        "environment": current_app.config["ENVIRONMENT"],
        "checks": checks,
    }
    return jsonify(payload), status_code


@bp.app_errorhandler(RequestEntityTooLarge)
def handle_large_upload(error: RequestEntityTooLarge):
    get_security_logger().warning(
        "upload_rejected_size_limit",
        extra={
            "event": "upload_rejected_size_limit",
            "max_content_length": current_app.config["MAX_CONTENT_LENGTH"],
        },
    )
    return _error_response(
        error, "Uploaded file exceeds the 5MB limit.", 413
    )

@bp.app_errorhandler(RateLimitExceeded)
def handle_rate_limit(error: RateLimitExceeded):
    get_security_logger().warning(
        "rate_limit_exceeded",
        extra={
            "event": "rate_limit_exceeded",
            "limit": str(error.description),
        },
    )
    return _error_response(
        error, "Too many requests. Please slow down and try again.", 429
    )

@bp.app_errorhandler(HTTPException)
def handle_http_exception(error: HTTPException):
    return _error_response(error, error.description, error.code or 500)

@bp.app_errorhandler(Exception)
def handle_unexpected_exception(error: Exception):
    db.session.rollback()
    current_app.logger.exception(
        "unhandled_exception", extra={"event": "unhandled_exception"}
    )
    return _error_response(error, "An unexpected error occurred.", 500)


def _error_response(error: Exception, message: str, status_code: int):
    payload = {
        "error": {
            "code": status_code,
            "name": getattr(error, "name", error.__class__.__name__),
            "message": message,
            "details": str(error),
        }
    }

    if _wants_json():
        return jsonify(payload), status_code

    template_name = f"errors/{status_code}.html"
    try:
        return render_template(template_name, **payload), status_code
    except TemplateNotFound:
        return jsonify(payload), status_code


def _wants_json() -> bool:
    if request.path.startswith("/api/"):
        return True
    best = request.accept_mimetypes.best_match(
        ["application/json", "text/html"]
    )
    return (
        best == "application/json"
        and request.accept_mimetypes[best]
        > request.accept_mimetypes["text/html"]
    )