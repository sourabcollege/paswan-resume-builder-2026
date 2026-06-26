from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from flask import current_app, render_template, url_for
from flask_mail import Message
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from jinja2 import TemplateNotFound

from app.extensions import mail
from app.models.user import User


EMAIL_VERIFICATION_SALT = "paswan-resume-builder-email-verification"
PASSWORD_RESET_SALT = "paswan-resume-builder-password-reset"


def generate_email_verification_token(user: User) -> str:
    serializer = _serializer(EMAIL_VERIFICATION_SALT)
    return serializer.dumps({"user_id": user.id, "email": user.email})


def confirm_email_verification_token(token: str) -> dict[str, Any] | None:
    serializer = _serializer(EMAIL_VERIFICATION_SALT)
    max_age = current_app.config["EMAIL_VERIFICATION_TOKEN_MAX_AGE_SECONDS"]
    return _loads(serializer, token, max_age)


def generate_password_reset_token(user: User) -> str:
    serializer = _serializer(PASSWORD_RESET_SALT)
    return serializer.dumps(
        {
            "user_id": user.id,
            "email": user.email,
            "password_changed_at": _token_timestamp(user.password_changed_at),
        }
    )


def confirm_password_reset_token(token: str) -> dict[str, Any] | None:
    serializer = _serializer(PASSWORD_RESET_SALT)
    max_age = current_app.config["PASSWORD_RESET_TOKEN_MAX_AGE_SECONDS"]
    return _loads(serializer, token, max_age)


def send_verification_email(user: User) -> bool:
    token = generate_email_verification_token(user)
    verify_url = url_for("auth.verify_email", token=token, _external=True)
    return send_auth_email(
        subject="Verify your Paswan Resume Builder account",
        recipients=[user.email],
        template_base="auth/email_verification",
        context={"user": user, "verify_url": verify_url, "expires_hours": 24},
    )


def send_password_reset_email(user: User) -> bool:
    token = generate_password_reset_token(user)
    reset_url = url_for("auth.reset_password", token=token, _external=True)
    return send_auth_email(
        subject="Reset your Paswan Resume Builder password",
        recipients=[user.email],
        template_base="auth/password_reset",
        context={"user": user, "reset_url": reset_url, "expires_minutes": 60},
    )


def send_welcome_email(user: User) -> bool:
    return send_auth_email(
        subject="Welcome to Paswan Resume Builder",
        recipients=[user.email],
        template_base="auth/welcome",
        context={"user": user},
    )


def send_auth_email(
    *,
    subject: str,
    recipients: list[str],
    template_base: str,
    context: dict[str, Any],
) -> bool:
    sender = current_app.config.get("MAIL_DEFAULT_SENDER")
    text_body = _render_email_template(f"{template_base}.txt", context) or _plain_text_fallback(subject, context)
    html_body = _render_email_template(f"{template_base}.html", context)
    message = Message(subject=subject, recipients=recipients, sender=sender, body=text_body, html=html_body)

    if current_app.config.get("MAIL_SUPPRESS_SEND"):
        current_app.logger.info(
            "mail_suppressed",
            extra={"event": "mail_suppressed", "subject": subject, "recipient_count": len(recipients)},
        )
        return False

    mail.send(message)
    current_app.logger.info(
        "mail_sent",
        extra={"event": "mail_sent", "subject": subject, "recipient_count": len(recipients)},
    )
    return True


def email_domain(email: str) -> str | None:
    if "@" not in (email or ""):
        return None
    return email.rsplit("@", 1)[1].lower()


def hash_request_value(value: str | None) -> str | None:
    if not value:
        return None
    salt = current_app.config.get("SECRET_KEY", "")
    digest = hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()
    return digest[:32]


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=salt)


def _loads(serializer: URLSafeTimedSerializer, token: str, max_age: int) -> dict[str, Any] | None:
    try:
        payload = serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    return payload if isinstance(payload, dict) else None


def _render_email_template(template_name: str, context: dict[str, Any]) -> str | None:
    try:
        return render_template(template_name, **context)
    except TemplateNotFound:
        return None


def _plain_text_fallback(subject: str, context: dict[str, Any]) -> str:
    user = context.get("user")
    greeting = f"Hello {getattr(user, 'first_name', 'there')},"
    if "verify_url" in context:
        return f"{greeting}\n\nPlease verify your account:\n{context['verify_url']}\n\nThis link expires in 24 hours."
    if "reset_url" in context:
        return f"{greeting}\n\nReset your password here:\n{context['reset_url']}\n\nThis link expires in 1 hour."
    return f"{greeting}\n\n{subject}"


def _token_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
