from __future__ import annotations

import re

from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, HiddenField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, ValidationError


PASSWORD_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


def _strip(value: str | None) -> str:
    return (value or "").strip()


def _lower(value: str | None) -> str:
    return _strip(value).lower()


class RegisterForm(FlaskForm):
    first_name = StringField("First name", filters=[_strip], validators=[DataRequired(), Length(min=2, max=120)])
    last_name = StringField("Last name", filters=[_strip], validators=[DataRequired(), Length(min=2, max=120)])
    email = EmailField("Email", filters=[_lower], validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=12, max=128)])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    accept_terms = BooleanField("Accept terms", validators=[DataRequired(message="You must accept the terms.")])
    next = HiddenField("Next", filters=[_strip], validators=[Optional(), Length(max=512)])
    submit = SubmitField("Create account")

    def validate_password(self, field: PasswordField) -> None:
        password = field.data or ""
        if not any(char.islower() for char in password):
            raise ValidationError("Password must include a lowercase letter.")
        if not any(char.isupper() for char in password):
            raise ValidationError("Password must include an uppercase letter.")
        if not any(char.isdigit() for char in password):
            raise ValidationError("Password must include a number.")
        if not PASSWORD_SPECIAL_RE.search(password):
            raise ValidationError("Password must include a symbol.")


class LoginForm(FlaskForm):
    email = EmailField("Email", filters=[_lower], validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
    remember = BooleanField("Remember me")
    next = HiddenField("Next", filters=[_strip], validators=[Optional(), Length(max=512)])
    submit = SubmitField("Sign in")


class EmailVerificationRequestForm(FlaskForm):
    email = EmailField("Email", filters=[_lower], validators=[DataRequired(), Email(), Length(max=255)])
    submit = SubmitField("Send verification email")


class PasswordResetRequestForm(FlaskForm):
    email = EmailField("Email", filters=[_lower], validators=[DataRequired(), Email(), Length(max=255)])
    submit = SubmitField("Send reset link")


class PasswordResetForm(FlaskForm):
    password = PasswordField("New password", validators=[DataRequired(), Length(min=12, max=128)])
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Update password")

    def validate_password(self, field: PasswordField) -> None:
        password = field.data or ""
        if not any(char.islower() for char in password):
            raise ValidationError("Password must include a lowercase letter.")
        if not any(char.isupper() for char in password):
            raise ValidationError("Password must include an uppercase letter.")
        if not any(char.isdigit() for char in password):
            raise ValidationError("Password must include a number.")
        if not PASSWORD_SPECIAL_RE.search(password):
            raise ValidationError("Password must include a symbol.")
class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField(
        "New password",
        validators=[DataRequired(), Length(min=12, max=128)]
    )
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords must match.")]
    )
    submit = SubmitField("Update password")

    def validate_new_password(self, field: PasswordField) -> None:
        password = field.data or ""
        if not any(char.islower() for char in password):
            raise ValidationError("Password must include a lowercase letter.")
        if not any(char.isupper() for char in password):
            raise ValidationError("Password must include an uppercase letter.")
        if not any(char.isdigit() for char in password):
            raise ValidationError("Password must include a number.")
        if not PASSWORD_SPECIAL_RE.search(password):
            raise ValidationError("Password must include a symbol.")
