from __future__ import annotations

from app.resume import bp

import json
from functools import wraps
from io import BytesIO
from typing import Any

from flask import Blueprint, abort, g, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user
from flask_wtf.csrf import generate_csrf
from jinja2 import TemplateNotFound
from werkzeug.datastructures import MultiDict

from app.auth.decorators import active_user_required
from app.auth.utils import hash_request_value
from app.extensions import limiter
from app.repositories.resumes import ResumeRepository
from app.resume.forms import (
    ExportForm,
    ResumeActionForm,
    ResumeBuilderForm,
    ResumeUploadForm,
    VersionCompareForm,
    VersionCreateForm,
    parse_json_object,
)
from app.services.resume_service import ResumeService, ResumeServiceResult


def _resume_owner_required(view):
    @wraps(view)
    @active_user_required
    def wrapped(resume_id: str, *args: Any, **kwargs: Any):
        resume = ResumeRepository().get_by_public_id_for_user(resume_id, current_user.id)
        if resume is None:
            if not _wants_json():
                abort(404, description="Resume not found.")
            return jsonify({"error": {"code": 404, "message": "Resume not found."}}), 404
        g.owned_resume = resume
        return view(resume_id, *args, **kwargs)

    return wrapped


@bp.get("")
@active_user_required
@limiter.limit("120 per hour")
def list_resumes():
    result = ResumeService().list_resumes(current_user.id)
    return _service_response(result, template_name="resume/list.html")


@bp.get("/<resume_id>")
@_resume_owner_required
@limiter.limit("120 per hour")
def resume_detail(resume_id: str):
    result = ResumeService().get_builder_payload(current_user.id, resume_id)
    return _service_response(result, template_name="resume/detail.html")


@bp.route("/upload", methods=["GET", "POST"])
@active_user_required
@limiter.limit("10 per hour")
def upload_resume():
    form = ResumeUploadForm()
    if request.method == "GET":
        return _render_or_json("resume/upload.html", form)
    if not form.validate_on_submit():
        return _validation_error(form, "resume/upload.html", {"form": form})

    result = ResumeService().upload_resume(
        current_user._get_current_object(),
        form.file.data,
        title=form.title.data,
        parse_immediately=bool(form.parse_immediately.data),
        request_meta=_request_meta(),
    )
    return _service_response(
        result,
        template_name="resume/upload.html",
        context={"form": form},
        success_redirect=url_for("resume.list_resumes"),
    )


@bp.post("/<resume_id>/parse")
@_resume_owner_required
@limiter.limit("10 per hour")
def parse_resume(resume_id: str):
    form = _form_from_request(ResumeActionForm)
    if not form.validate_on_submit():
        return _validation_error(form)
    result = ResumeService().parse_resume(current_user.id, resume_id, request_meta=_request_meta())
    return _service_response(result)


@bp.post("/<resume_id>/delete")
@_resume_owner_required
@limiter.limit("30 per hour")
def delete_resume(resume_id: str):
    form = _form_from_request(ResumeActionForm)
    if not form.validate_on_submit():
        return _validation_error(form)
    result = ResumeService().delete_resume(
        current_user.id,
        resume_id,
        request_meta=_request_meta(),
    )
    return _service_response(
        result,
        success_redirect=url_for("resume.list_resumes"),
    )


# ── FIXED: GET handler now passes empty resume/version so builder.html doesn't crash ──
@bp.route("/builder", methods=["GET", "POST"])
@active_user_required
@limiter.limit("30 per hour")
def create_builder_resume():
    form = _form_from_request(ResumeBuilderForm)
    if request.method == "GET":
        if _wants_json():
            return jsonify(_form_schema(form, generate_csrf()))
        return render_template(
            "resume/builder.html",
            form=form,
            resume={"id": "", "title": "", "template": "classic"},
            version={"label": "", "content": {}},
            mode="create",
        )
    if not form.validate_on_submit():
        return _validation_error(form)

    payload = _builder_payload(form)
    result = ResumeService().create_builder_resume(
        current_user._get_current_object(),
        payload,
        request_meta=_request_meta(),
    )
    return _service_response(result)


@bp.route("/<resume_id>/builder", methods=["GET", "POST"])
@_resume_owner_required
@limiter.limit("180 per hour")
def edit_builder_resume(resume_id: str):
    if request.method == "GET":
        result = ResumeService().get_builder_payload(current_user.id, resume_id)
        form = ResumeBuilderForm()
        if result.success and result.data.get("resume"):
            resume = result.data.get("resume") or {}
            version = result.data.get("version") or {}
            form.title.data = resume.get("title")
            form.template_key.data = version.get("template_key") or "classic"
            form.content.data = json.dumps(version.get("content") or {}, indent=2)
            form.label.data = version.get("label")
        return _service_response(result, template_name="resume/builder.html", context={"form": form, "mode": "edit"})

    form = _form_from_request(ResumeBuilderForm)
    if not form.validate_on_submit():
        return _validation_error(form)
    result = ResumeService().save_builder_draft(
        current_user.id,
        resume_id,
        _builder_payload(form),
        request_meta=_request_meta(),
    )
    return _service_response(result)


@bp.get("/<resume_id>/versions")
@_resume_owner_required
@limiter.limit("120 per hour")
def list_versions(resume_id: str):
    result = ResumeService().list_versions(current_user.id, resume_id)
    return _service_response(result, template_name="resume/versions.html")


@bp.post("/<resume_id>/versions")
@_resume_owner_required
@limiter.limit("30 per hour")
def create_version(resume_id: str):
    form = _form_from_request(VersionCreateForm)
    if not form.validate_on_submit():
        return _validation_error(form)
    payload: dict[str, Any] = {
        "label": form.label.data,
        "change_summary": form.change_summary.data,
        "template_key": form.template_key.data,
        "make_current": bool(form.make_current.data),
    }
    if form.content.data:
        payload["content"] = parse_json_object(form.content.data)
    result = ResumeService().create_version(current_user.id, resume_id, payload, request_meta=_request_meta())
    return _service_response(result)


@bp.get("/<resume_id>/versions/<version_id>")
@_resume_owner_required
@limiter.limit("120 per hour")
def version_detail(resume_id: str, version_id: str):
    result = ResumeService().get_version(current_user.id, resume_id, version_id)
    return _service_response(result, template_name="resume/version_detail.html")


@bp.post("/<resume_id>/versions/<version_id>/restore")
@_resume_owner_required
@limiter.limit("20 per hour")
def restore_version(resume_id: str, version_id: str):
    form = _form_from_request(ResumeActionForm)
    if not form.validate_on_submit():
        return _validation_error(form)
    result = ResumeService().restore_version(
        current_user.id,
        resume_id,
        version_id,
        request_meta=_request_meta(),
    )
    return _service_response(result)


@bp.post("/<resume_id>/versions/compare")
@_resume_owner_required
@limiter.limit("30 per hour")
def compare_versions(resume_id: str):
    form = _form_from_request(VersionCompareForm)
    if not form.validate_on_submit():
        return _validation_error(form)
    result = ResumeService().compare_versions(
        current_user.id,
        resume_id,
        form.left_version_id.data,
        form.right_version_id.data,
    )
    return _service_response(result)


# ── FIXED: GET + POST both allowed for export ──
@bp.route("/<resume_id>/export/<export_format>", methods=["GET", "POST"])
@_resume_owner_required
@limiter.limit("30 per hour")
def export_resume(resume_id: str, export_format: str):
    version_id = None
    as_attachment = export_format.lower() != "html"

    # POST: validate form, use version_id from form
    if request.method == "POST":
        form = _form_from_request(ExportForm)
        if not form.validate_on_submit():
            return _validation_error(form)
        version_id = form.version_id.data or None
        as_attachment = bool(form.download.data) or export_format.lower() != "html"

    result = ResumeService().export_resume(
        current_user.id,
        resume_id,
        export_format,
        version_id,
        request_meta=_request_meta(),
    )
    if not result.success:
        return _service_response(result)

    artifact = result.data["export"]
    return send_file(
        BytesIO(artifact.data),
        mimetype=artifact.mimetype,
        as_attachment=as_attachment,
        download_name=artifact.filename,
        max_age=0,
    )


def _form_from_request(form_class):
    if request.method == "GET":
        return form_class()
    payload = request.get_json(silent=True) if request.is_json else request.form.to_dict(flat=True)
    payload = dict(payload or {})
    for key, value in list(payload.items()):
        if isinstance(value, (dict, list)):
            payload[key] = json.dumps(value)
    csrf_value = request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
    if csrf_value and "csrf_token" not in payload:
        payload["csrf_token"] = csrf_value
    return form_class(formdata=MultiDict(payload))


def _builder_payload(form: ResumeBuilderForm) -> dict[str, Any]:
    return {
        "title": form.title.data,
        "template_key": form.template_key.data,
        "content": parse_json_object(form.content.data),
        "label": form.label.data,
        "change_summary": form.change_summary.data,
    }


def _service_response(
    result: ResumeServiceResult,
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
                ), result.status_code
        return jsonify({"message": result.message, **result.data}), result.status_code
    if not _wants_json() and template_name:
        return render_template(
            template_name,
            **(context or {}),
            **result.data,
            message=result.message,
            errors=result.errors,
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
            errors=errors,
            message="Please correct the highlighted fields.",
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


def _render_or_json(template_name: str, form):
    csrf_value = generate_csrf()
    if _wants_json():
        return jsonify(_form_schema(form, csrf_value))
    try:
        return render_template(template_name, form=form)
    except TemplateNotFound:
        return jsonify(_form_schema(form, csrf_value))


def _form_schema(form, csrf_token_value: str) -> dict[str, Any]:
    return {
        "csrf_token": csrf_token_value,
        "fields": [
            {"name": name, "label": field.label.text, "type": field.type}
            for name, field in form._fields.items()
            if name not in {"csrf_token", "submit"}
        ],
    }


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