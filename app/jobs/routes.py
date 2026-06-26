from __future__ import annotations

from app.jobs import bp

from typing import Any

from flask import Blueprint, g, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf.csrf import generate_csrf
from werkzeug.datastructures import MultiDict

from app.auth.decorators import active_user_required
from app.auth.utils import hash_request_value
from app.extensions import limiter
from app.jobs.forms import JobApplyForm, JobMatchForm, JobRecommendationForm, JobSearchForm, JobTrackingForm
from app.services.job_service import JobService, JobServiceResult





@bp.get("")
@active_user_required
@limiter.limit("120 per hour")
def list_jobs():
    form = JobSearchForm(request.args)
    if not form.validate():
        return _validation_error(form, template_name="jobs/list.html")
    filters = {
        "q": form.q.data,
        "location": form.location.data,
        "experience_level": form.experience_level.data,
        "workplace_type": form.workplace_type.data,
        "employment_type": form.employment_type.data,
        "limit": form.limit.data,
        "offset": form.offset.data,
    }
    service = JobService()
    if _wants_json():
        result = service.list_jobs(current_user._get_current_object(), filters)
    else:
        result = service.list_jobs_for_page(current_user._get_current_object(), filters)
    return _service_response(result, template_name="jobs/list.html", context={"form": form, "filters": filters})


@bp.get("/recommendations")
@active_user_required
@limiter.limit("20 per hour")
def recommendations():
    form = JobRecommendationForm(request.args)
    if not form.validate():
        return _validation_error(form)
    result = JobService().recommend_top_jobs(
        current_user._get_current_object(),
        form.resume_id.data,
        form.version_id.data or None,
        request_meta=_request_meta(),
    )
    return _service_response(result)


@bp.get("/applications")
@active_user_required
@limiter.limit("120 per hour")
def tracked_jobs():
    return _service_response(JobService().list_tracked_jobs(current_user._get_current_object()))


@bp.get("/<job_id>")
@active_user_required
@limiter.limit("120 per hour")
def job_detail(job_id: str):
    service = JobService()
    if _wants_json():
        result = service.get_job(current_user._get_current_object(), job_id)
    else:
        result = service.get_job_for_page(current_user._get_current_object(), job_id)
    return _service_response(result, template_name="jobs/detail.html")


@bp.post("/<job_id>/match")
@active_user_required
@limiter.limit("30 per hour")
def match_job(job_id: str):
    form = _form_from_request(JobMatchForm)
    if not form.validate_on_submit():
        return _validation_error(form)
    result = JobService().match_job(
        current_user._get_current_object(),
        job_id,
        form.resume_id.data,
        form.version_id.data or None,
        request_meta=_request_meta(),
    )
    return _service_response(result)


@bp.post("/<job_id>/apply")
@active_user_required
@limiter.limit("20 per hour")
def apply_to_job(job_id: str):
    form = _form_from_request(JobApplyForm)
    if not form.validate_on_submit():
        return _validation_error(form, template_name="jobs/detail.html")
    result = JobService().apply_to_job(
        current_user._get_current_object(),
        job_id,
        form.resume_id.data,
        form.version_id.data or None,
        request_meta=_request_meta(),
    )
    return _service_response(
        result,
        template_name="jobs/detail.html",
        success_redirect=url_for("jobs.job_detail", job_id=job_id) if result.success and not _wants_json() else None,
    )


@bp.post("/<job_id>/track")
@active_user_required
@limiter.limit("30 per hour")
def update_tracking(job_id: str):
    form = _form_from_request(JobTrackingForm)
    if not form.validate_on_submit():
        return _validation_error(form)
    result = JobService().update_tracking_status(
        current_user._get_current_object(),
        job_id,
        form.resume_id.data,
        form.status.data,
        form.version_id.data or None,
        request_meta=_request_meta(),
    )
    return _service_response(result)


def _form_from_request(form_class):
    payload = request.get_json(silent=True) if request.is_json else request.form.to_dict(flat=True)
    payload = dict(payload or {})
    csrf_value = request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
    if csrf_value and "csrf_token" not in payload:
        payload["csrf_token"] = csrf_value
    return form_class(formdata=MultiDict(payload))


def _service_response(
    result: JobServiceResult,
    *,
    template_name: str | None = None,
    context: dict[str, Any] | None = None,
    success_redirect: str | None = None,
):
    if result.success:
        if not _wants_json():
            if success_redirect:
                return redirect(success_redirect)
            if template_name:
                return render_template(
                    template_name,
                    **(context or {}),
                    **result.data,
                    message=result.message,
                    csrf_token=generate_csrf(),
                ), result.status_code
        return jsonify({"message": result.message, **result.data}), result.status_code
    if not _wants_json() and template_name:
        return render_template(
            template_name,
            **(context or {}),
            **result.data,
            message=result.message,
            errors=result.errors,
            csrf_token=generate_csrf(),
        ), result.status_code
    return jsonify(
        {
            "error": {
                "code": result.status_code,
                "message": result.message,
                "fields": result.errors,
            },
            **result.data,
        }
    ), result.status_code


def _validation_error(form, template_name: str | None = None, context: dict[str, Any] | None = None):
    errors = {name: list(messages) for name, messages in form.errors.items()}
    if template_name and not _wants_json():
        render_context = dict(context or {})
        render_context["form"] = form
        return render_template(
            template_name,
            **render_context,
            jobs=[],
            errors=errors,
            message="Please correct the highlighted fields.",
            csrf_token=generate_csrf(),
        ), 400
    return jsonify(
        {
            "error": {
                "code": 400,
                "message": "Please correct the highlighted fields.",
                "fields": errors,
            }
        }
    ), 400


def _request_meta() -> dict[str, Any]:
    remote_addr = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",", 1)[0].strip()
    return {
        "request_id": getattr(g, "request_id", None) or request.headers.get("X-Request-ID"),
        "remote_addr_hash": hash_request_value(remote_addr),
        "user_agent_hash": hash_request_value(request.headers.get("User-Agent", "")),
    }


def _wants_json() -> bool:
    if request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] >= request.accept_mimetypes["text/html"]
