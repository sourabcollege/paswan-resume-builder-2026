from __future__ import annotations

from app.auth import bp

from urllib.parse import urlparse

from flask import Blueprint, abort, current_app, g, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import generate_csrf
from jinja2 import TemplateNotFound
from werkzeug.datastructures import MultiDict

from app.auth.forms import (
    EmailVerificationRequestForm,
    LoginForm,
    PasswordResetForm,
    PasswordResetRequestForm,
    RegisterForm,
)
from app.auth.utils import hash_request_value
from app.extensions import limiter, oauth
from app.services.auth_service import AuthResult, AuthService


@bp.get("/csrf-token")
@limiter.limit("60 per minute")
def csrf_token():
    return jsonify({"csrf_token": generate_csrf()})


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("1000 per hour")
def register():
    if current_user.is_authenticated:
        return _success({"message": "You are already signed in."})

    form = _form_from_request(RegisterForm)
    if request.method == "GET":
        return _render_or_json(
            "auth/register.html",
            {"form": form, "csrf_token": generate_csrf()},
        )

    if not form.validate_on_submit():
        return _validation_error(form, "auth/register.html")

    result = AuthService().register_user(
        {
            "first_name": form.first_name.data,
            "last_name": form.last_name.data,
            "email": form.email.data,
            "password": form.password.data,
        },
        request_meta=_request_meta(),
    )
    if not result.success and not _wants_json():
        return render_template(
            "auth/register.html",
            form=form,
            csrf_token=generate_csrf(),
            message=result.message,
            errors=result.errors,
        ), result.status_code
    if result.success and not _wants_json():
        return redirect(url_for("auth.login", registered="1"))
    return _auth_result_response(result)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("1000 per hour")
def login():
    if current_user.is_authenticated:
        return _success({"message": "You are already signed in."})

    form = _form_from_request(LoginForm)
    if request.method == "GET":
        return _render_or_json(
            "auth/login.html",
            {
                "form": form,
                "csrf_token": generate_csrf(),
                "registered": request.args.get("registered") == "1",
                "verified": request.args.get("verified") == "1",
                "reset": request.args.get("reset") == "1",
            },
        )

    if not form.validate_on_submit():
        return _validation_error(form, "auth/login.html")

    result = AuthService().authenticate_user(form.email.data, form.password.data, request_meta=_request_meta())
    if not result.success or result.user is None:
        if not _wants_json():
            return render_template(
                "auth/login.html",
                form=form,
                csrf_token=generate_csrf(),
                message=result.message,
                errors=result.errors,
            ), result.status_code
        return _auth_result_response(result)

    login_user(result.user, remember=bool(form.remember.data), fresh=True)

    # ✅ Double-check admin role assignment after login
    AuthService.ensure_admin_role(result.user)

    next_url = _safe_next_url(form.next.data)
    payload = {"message": result.message, "user": _public_user(result.user), "redirect": next_url or url_for("main.dashboard")}
    return _success(payload)


@bp.route("/logout", methods=["GET", "POST"])
@login_required
@limiter.limit("30 per minute")
def logout():
    user = current_user._get_current_object()
    AuthService().record_logout(user, request_meta=_request_meta(actor_user_id=user.id))
    logout_user()
    return _success({"message": "Signed out successfully.", "redirect": url_for("main.index")})


# ── GOOGLE OAUTH ──
@bp.route("/google")
def google_login():
    """Redirect to Google for OAuth authentication."""
    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@bp.route("/google/callback")
def google_callback():
    """Handle Google OAuth callback."""
    try:
        token = oauth.google.authorize_access_token()
    except Exception as exc:
        current_app.logger.error(f"Google OAuth error: {exc}")
        return _error("Google authentication failed. Please try again.", 400)

    user_info = token.get("userinfo")
    if not user_info:
        return _error("Could not retrieve user info from Google.", 400)

    result = AuthService().authenticate_google_user(
        google_id=str(user_info.get("sub")),
        email=user_info.get("email", ""),
        first_name=user_info.get("given_name", ""),
        last_name=user_info.get("family_name", ""),
    )

    if result.success and result.user:
        login_user(result.user, remember=True, fresh=True)

        # ✅ Double-check admin role assignment after Google login
        AuthService.ensure_admin_role(result.user)

        next_url = request.args.get("next")
        payload = {
            "message": result.message,
            "user": _public_user(result.user),
            "redirect": next_url or url_for("main.dashboard"),
        }
        return _success(payload)

    return _auth_result_response(result)


@bp.route("/verify-email/<token>", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def verify_email(token: str):
    service = AuthService()
    if request.method == "GET":
        validation = service.validate_email_verification_token(token)
        if not validation.success:
            return _render_or_json(
                "auth/verify_email.html",
                {"csrf_token": generate_csrf(), "message": validation.message},
            )
        return _render_or_json(
            "auth/verify_email.html",
            {"csrf_token": generate_csrf(), "message": "Confirm your email verification."},
        )

    result = service.verify_email(token, request_meta=_request_meta())
    if result.success and not _wants_json():
        redirect_url = result.meta.get("redirect") or url_for("auth.login", verified="1")
        return redirect(redirect_url)
    return _auth_result_response(result)


@bp.route("/resend-verification", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def resend_verification():
    form = _form_from_request(EmailVerificationRequestForm)
    if request.method == "GET":
        return _render_or_json("auth/resend_verification.html", {"form": form, "csrf_token": generate_csrf()})

    if not form.validate_on_submit():
        return _validation_error(form, "auth/resend_verification.html")

    result = AuthService().send_verification_email(form.email.data, request_meta=_request_meta())
    if not _wants_json():
        return render_template(
            "auth/resend_verification.html",
            form=EmailVerificationRequestForm(),
            csrf_token=generate_csrf(),
            success_message=result.message if result.success else None,
            message=None if result.success else result.message,
        ), result.status_code
    return _auth_result_response(result)


@bp.route("/password-reset", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def password_reset_request():
    form = _form_from_request(PasswordResetRequestForm)
    if request.method == "GET":
        return _render_or_json(
            "auth/forgot_password.html",
            {"form": form, "csrf_token": generate_csrf()},
        )

    if not form.validate_on_submit():
        return _validation_error(form, "auth/forgot_password.html")

    result = AuthService().request_password_reset(form.email.data, request_meta=_request_meta())
    if not _wants_json():
        return render_template(
            "auth/forgot_password.html",
            form=PasswordResetRequestForm(),
            csrf_token=generate_csrf(),
            success_message=result.message,
        ), result.status_code
    return _auth_result_response(result)

# ── GOOGLE OAUTH DEV BYPASS (for testing without real credentials) ──
@bp.route("/google-dev")
def google_dev_login():
    """Dev bypass: simulates Google login without real OAuth credentials."""
    if not current_app.config.get("DEBUG"):
        abort(404)

    # Create or login a mock Google user
    from app.services.auth_service import AuthService
    result = AuthService().authenticate_google_user(
        google_id="dev-google-id-12345",
        email="devuser@example.com",
        first_name="Dev",
        last_name="User",
    )

    if result.success and result.user:
        login_user(result.user, remember=True, fresh=True)

        # ✅ Double-check admin role assignment after dev login
        AuthService.ensure_admin_role(result.user)

        return redirect(url_for("main.dashboard"))

    return _error("Dev login failed", 500)


@bp.route("/password-reset/<token>", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def reset_password(token: str):
    service = AuthService()
    if request.method == "GET":
        validation = service.validate_password_reset_token(token)
        if not validation.success:
            return _auth_result_response(validation)
        form = _form_from_request(PasswordResetForm)
        return _render_or_json("auth/password_reset.html", {"form": form, "csrf_token": generate_csrf()})

    form = _form_from_request(PasswordResetForm)
    if not form.validate_on_submit():
        return _validation_error(form)

    result = service.reset_password(token, form.password.data, request_meta=_request_meta())
    return _auth_result_response(result)


def _form_from_request(form_class):
    if request.method == "GET":
        return form_class()

    payload = request.get_json(silent=True) if request.is_json else request.form.to_dict(flat=True)
    payload = dict(payload or {})
    csrf_value = (
        request.headers.get("X-CSRFToken")
        or request.headers.get("X-CSRF-Token")
        or request.headers.get("X-XSRF-TOKEN")
    )
    if csrf_value and "csrf_token" not in payload:
        payload["csrf_token"] = csrf_value
    return form_class(formdata=MultiDict(payload))


def _auth_result_response(result: AuthResult):
    payload = {"message": result.message, **result.meta}
    if result.user is not None:
        payload["user"] = _public_user(result.user)
    if result.success:
        return _success(payload, result.status_code)
    return _error(result.message, result.status_code, result.errors, result.meta)


def _validation_error(form, template_name: str | None = None):
    if template_name and not _wants_json():
        return render_template(
            template_name,
            form=form,
            csrf_token=generate_csrf(),
            errors=_form_errors(form),
        ), 400
    return _error("Please correct the highlighted fields.", 400, _form_errors(form))


def _success(payload: dict, status_code: int = 200):
    if _wants_json():
        return jsonify(payload), status_code
    redirect_url = payload.get("redirect")
    if redirect_url:
        return redirect(redirect_url)
    return jsonify(payload), status_code


def _error(
    message: str,
    status_code: int,
    errors: dict[str, list[str]] | None = None,
    meta: dict | None = None,
):
    payload = {"error": {"code": status_code, "message": message, "fields": errors or {}}}
    if meta:
        payload["error"]["meta"] = meta
    return jsonify(payload), status_code


def _render_or_json(template_name: str, context: dict, status_code: int = 200):
    if _wants_json():
        return jsonify(_form_payload(context.get("form"), context.get("csrf_token"), context.get("message"))), status_code
    try:
        return render_template(template_name, **context), status_code
    except TemplateNotFound:
        return jsonify(_form_payload(context.get("form"), context.get("csrf_token"), context.get("message"))), status_code


def _form_payload(form, csrf_token_value: str | None, message: str | None = None) -> dict:
    payload = {"csrf_token": csrf_token_value, "fields": []}
    fields = []
    if form is not None:
        for name, field in form._fields.items():
            if name in {"csrf_token", "submit"}:
                continue
            fields.append({"name": name, "label": field.label.text, "type": field.type})
    payload["fields"] = fields
    if message:
        payload["message"] = message
    return payload


def _form_errors(form) -> dict[str, list[str]]:
    return {field: list(messages) for field, messages in form.errors.items()}


def _public_user(user) -> dict:
    return {
        "id": user.public_id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role,
        "account_status": user.account_status,
        "email_verified": user.is_email_verified,
    }


def _safe_next_url(next_url: str | None) -> str | None:
    if not next_url:
        return None
    parsed = urlparse(next_url)
    if parsed.netloc or parsed.scheme:
        return None
    if not next_url.startswith("/"):
        return None
    return next_url


def _request_meta(actor_user_id: int | None = None) -> dict:
    remote_addr = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",", 1)[0].strip()
    user_agent = request.headers.get("User-Agent", "")
    return {
        "actor_user_id": actor_user_id,
        "request_id": getattr(g, "request_id", None) or request.headers.get("X-Request-ID"),
        "remote_addr_hash": hash_request_value(remote_addr),
        "user_agent_hash": hash_request_value(user_agent),
    }


def _wants_json() -> bool:
    if request.is_json or request.path.startswith("/api/"):
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] >= request.accept_mimetypes["text/html"]