from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from flask import current_app, url_for
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.exc import IntegrityError

from app.extensions import db, mail
from app.models.user import User
from flask_mail import Message


@dataclass(frozen=True)
class AuthResult:
    success: bool
    message: str
    user: User | None = None
    status_code: int = 200
    errors: dict[str, list[str]] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


class AuthService:
    # ── Admin Role Assignment ──
    @staticmethod
    def ensure_admin_role(user: User) -> bool:
        """If user's email matches ADMIN_EMAIL, promote to admin. Returns True if changed."""
        admin_email = current_app.config.get("ADMIN_EMAIL", "")
        if not admin_email:
            return False
        if user.can_be_admin(admin_email) and user.role != User.ROLE_ADMIN:
            user.role = User.ROLE_ADMIN
            db.session.add(user)
            db.session.commit()
            current_app.logger.info(f"Promoted user {user.email} to admin role.")
            return True
        return False

    # ── Registration ──
    def register_user(
        self,
        data: dict[str, Any],
        request_meta: dict[str, Any] | None = None,
    ) -> AuthResult:
        email = data.get("email", "").lower().strip()
        existing = User.query.filter_by(email=email).first()
        if existing:
            return AuthResult(
                False,
                "An account with this email already exists.",
                status_code=409,
                errors={"email": ["Email already registered."]},
            )

        user = User(
            email=email,
            first_name=data.get("first_name", "").strip(),
            last_name=data.get("last_name", "").strip(),
            account_status=User.STATUS_ACTIVE,
        )
        user.set_password(data["password"])
        db.session.add(user)

        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            return AuthResult(
                False,
                "An account with this email already exists.",
                status_code=409,
                errors={"email": ["Email already registered."]},
            )

        self._send_verification_email(user)
        db.session.commit()

        # ✅ Auto-assign admin if email matches
        self.ensure_admin_role(user)

        return AuthResult(
            True,
            "Account created. Please verify your email.",
            user=user,
            status_code=201,
        )

    # ── Authentication ──
    def authenticate_user(
        self,
        email: str,
        password: str,
        request_meta: dict[str, Any] | None = None,
    ) -> AuthResult:
        user = User.query.filter_by(email=email.lower().strip()).first()
        if not user or not user.check_password(password):
            return AuthResult(
                False,
                "Invalid email or password.",
                status_code=401,
                errors={"credentials": ["Invalid email or password."]},
            )

        if user.account_status == User.STATUS_BANNED:
            return AuthResult(False, "Your account has been banned.", status_code=403)
        if user.account_status == User.STATUS_SUSPENDED:
            return AuthResult(False, "Your account has been suspended.", status_code=403)

        user.last_login_at = datetime.now(timezone.utc)
        user.failed_login_count = 0
        db.session.commit()

        # ✅ Auto-assign admin if email matches on every login
        self.ensure_admin_role(user)

        return AuthResult(True, "Signed in successfully.", user=user)

    # ── GOOGLE OAUTH ──
    def authenticate_google_user(
        self,
        google_id: str,
        email: str,
        first_name: str,
        last_name: str,
    ) -> AuthResult:
        """Login or create user via Google OAuth."""
        if not google_id or not email:
            return AuthResult(False, "Invalid Google credentials.", status_code=400)

        # 1. Check if user exists with this google_id
        user = User.query.filter_by(google_id=google_id).first()
        if user:
            user.last_login_at = datetime.now(timezone.utc)
            db.session.commit()
            self.ensure_admin_role(user)
            return AuthResult(True, "Signed in with Google.", user=user)

        # 2. Check if user exists with this email (link Google account)
        user = User.query.filter_by(email=email.lower().strip()).first()
        if user:
            user.google_id = google_id
            user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
            user.last_login_at = datetime.now(timezone.utc)
            db.session.commit()
            self.ensure_admin_role(user)
            return AuthResult(True, "Google account linked successfully.", user=user)

        # 3. Create new user with Google
        import bcrypt
        random_password = secrets.token_urlsafe(32)
        password_hash = bcrypt.hashpw(
            random_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        user = User(
            email=email.lower().strip(),
            first_name=first_name.strip() or "Google",
            last_name=last_name.strip() or "User",
            google_id=google_id,
            password_hash=password_hash,
            account_status=User.STATUS_ACTIVE,
            email_verified_at=datetime.now(timezone.utc),
        )
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return AuthResult(
                False,
                "An account with this email already exists.",
                status_code=409,
            )

        # ✅ Auto-assign admin if email matches
        self.ensure_admin_role(user)

        return AuthResult(
            True,
            "Account created with Google.",
            user=user,
            status_code=201,
        )

    # ── Email Verification ──
    def send_verification_email(
        self,
        email: str,
        request_meta: dict[str, Any] | None = None,
    ) -> AuthResult:
        user = User.query.filter_by(email=email.lower().strip()).first()
        if not user:
            return AuthResult(False, "User not found.", status_code=404)
        if user.is_email_verified:
            return AuthResult(False, "Email is already verified.", status_code=400)

        result = self._send_verification_email(user)
        return result

    def validate_email_verification_token(self, token: str) -> AuthResult:
        email = self._verify_token(token, "verify-email")
        if email is None:
            return AuthResult(
                False,
                "The verification link is invalid or has expired.",
                status_code=400,
            )
        user = User.query.filter_by(email=email).first()
        if not user:
            return AuthResult(False, "User not found.", status_code=404)
        return AuthResult(True, "Token is valid.", user=user)

    def verify_email(
        self,
        token: str,
        request_meta: dict[str, Any] | None = None,
    ) -> AuthResult:
        validation = self.validate_email_verification_token(token)
        if not validation.success:
            return validation

        user = validation.user
        if user.is_email_verified:
            return AuthResult(True, "Email is already verified.", user=user)

        user.email_verified_at = datetime.now(timezone.utc)
        user.account_status = User.STATUS_ACTIVE
        db.session.commit()

        return AuthResult(
            True,
            "Email verified successfully! You can now log in.",
            user=user,
            meta={"redirect": url_for("auth.login", verified="1", _external=False)},
        )

    # ── Password Reset ──
    def request_password_reset(
        self,
        email: str,
        request_meta: dict[str, Any] | None = None,
    ) -> AuthResult:
        user = User.query.filter_by(email=email.lower().strip()).first()
        if not user:
            return AuthResult(
                True,
                "If an account exists, a password reset email has been sent.",
            )

        token = self._generate_token(user.email, "reset-password")
        reset_url = url_for("auth.reset_password", token=token, _external=True)

        if not current_app.config.get("MAIL_SUPPRESS_SEND"):
            try:
                msg = Message(
                    subject="Reset your password — Paswan Resume",
                    sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
                    recipients=[user.email],
                    body=f"Reset your password: {reset_url}",
                    html=f"""
                    <p>Hello {user.first_name or 'there'},</p>
                    <p>You requested a password reset. Click the link below:</p>
                    <p><a href="{reset_url}">{reset_url}</a></p>
                    <p>If you didn't request this, ignore this email.</p>
                    """,
                )
                mail.send(msg)
            except Exception as exc:
                current_app.logger.error(f"Password reset email failed: {exc}")

        current_app.logger.info(f"Password reset URL for {user.email}: {reset_url}")
        return AuthResult(
            True,
            "If an account exists, a password reset email has been sent.",
        )

    def validate_password_reset_token(self, token: str) -> AuthResult:
        email = self._verify_token(token, "reset-password")
        if email is None:
            return AuthResult(
                False,
                "The password reset link is invalid or has expired.",
                status_code=400,
            )
        user = User.query.filter_by(email=email).first()
        if not user:
            return AuthResult(False, "User not found.", status_code=404)
        return AuthResult(True, "Token is valid.", user=user)

    def reset_password(
        self,
        token: str,
        new_password: str,
        request_meta: dict[str, Any] | None = None,
    ) -> AuthResult:
        validation = self.validate_password_reset_token(token)
        if not validation.success:
            return validation

        user = validation.user
        user.set_password(new_password)
        user.password_changed_at = datetime.now(timezone.utc)
        db.session.commit()

        return AuthResult(
            True,
            "Password reset successfully! Please log in with your new password.",
            meta={"redirect": url_for("auth.login", reset="1", _external=False)},
        )

    # ── Logout ──
    def record_logout(
        self,
        user: User,
        request_meta: dict[str, Any] | None = None,
    ) -> None:
        user.last_seen_at = datetime.now(timezone.utc)
        db.session.commit()

    # ── Helpers ──
    def _generate_token(self, email: str, salt: str) -> str:
        serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
        return serializer.dumps(email, salt=salt)

    def _verify_token(self, token: str, salt: str, max_age: int = 86400) -> str | None:
        serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
        try:
            return serializer.loads(token, salt=salt, max_age=max_age)
        except (BadSignature, SignatureExpired):
            return None

    def _send_verification_email(self, user: User) -> AuthResult:
        token = self._generate_token(user.email, "verify-email")
        verify_url = url_for("auth.verify_email", token=token, _external=True)

        if not current_app.config.get("MAIL_SUPPRESS_SEND"):
            try:
                msg = Message(
                    subject="Verify your email — Paswan Resume",
                    sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
                    recipients=[user.email],
                    body=f"Verify your email: {verify_url}",
                    html=f"""
                    <p>Hello {user.first_name or 'there'},</p>
                    <p>Welcome to Paswan Resume Builder! Click the link below to verify your email:</p>
                    <p><a href="{verify_url}">{verify_url}</a></p>
                    <p>If you didn't create an account, ignore this email.</p>
                    """,
                )
                mail.send(msg)
            except Exception as exc:
                current_app.logger.error(f"Verification email failed: {exc}")

        current_app.logger.info(f"Verification URL for {user.email}: {verify_url}")

        return AuthResult(
            True,
            "Verification email sent. Please check your inbox.",
            meta={"verify_url": verify_url if current_app.config.get("DEBUG") else None},
        )