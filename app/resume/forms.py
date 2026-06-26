from __future__ import annotations

import json
import re

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import BooleanField, HiddenField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, Regexp, ValidationError


TEMPLATE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


def _strip(value: str | None) -> str:
    return (value or "").strip()


class ResumeUploadForm(FlaskForm):
    title = StringField("Resume title", filters=[_strip], validators=[Optional(), Length(max=180)])
    file = FileField("Resume file", validators=[FileRequired(message="Select a PDF or DOCX resume.")])
    parse_immediately = BooleanField("Parse immediately", default=True)
    submit = SubmitField("Upload resume")


class ResumeBuilderForm(FlaskForm):
    title = StringField("Resume title", filters=[_strip], validators=[DataRequired(), Length(max=180)])
    template_key = StringField(
        "Template",
        filters=[_strip],
        default="classic",
        validators=[DataRequired(), Regexp(TEMPLATE_KEY_RE, message="Invalid template identifier.")],
    )
    content = TextAreaField("Resume content", validators=[DataRequired()])
    label = StringField("Version label", filters=[_strip], validators=[Optional(), Length(max=180)])
    change_summary = StringField("Change summary", filters=[_strip], validators=[Optional(), Length(max=500)])
    submit = SubmitField("Save resume")

    def validate_content(self, field: TextAreaField) -> None:
        _validate_json_object(field.data)


class VersionCreateForm(FlaskForm):
    label = StringField("Version label", filters=[_strip], validators=[Optional(), Length(max=180)])
    change_summary = StringField("Change summary", filters=[_strip], validators=[Optional(), Length(max=500)])
    template_key = StringField(
        "Template",
        filters=[_strip],
        validators=[Optional(), Regexp(TEMPLATE_KEY_RE, message="Invalid template identifier.")],
    )
    content = TextAreaField("Resume content", validators=[Optional()])
    make_current = BooleanField("Make current", default=True)
    submit = SubmitField("Create version")

    def validate_content(self, field: TextAreaField) -> None:
        if field.data:
            _validate_json_object(field.data)


class VersionCompareForm(FlaskForm):
    left_version_id = StringField("Left version", filters=[_strip], validators=[DataRequired(), Length(min=36, max=36)])
    right_version_id = StringField("Right version", filters=[_strip], validators=[DataRequired(), Length(min=36, max=36)])
    submit = SubmitField("Compare versions")


class ExportForm(FlaskForm):
    version_id = HiddenField("Version", filters=[_strip], validators=[Optional(), Length(min=36, max=36)])
    download = BooleanField("Download", default=True)
    submit = SubmitField("Export resume")


class ResumeActionForm(FlaskForm):
    submit = SubmitField("Confirm")


def parse_json_object(value: str | None) -> dict:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Resume content must be a JSON object.")
    return parsed


def _validate_json_object(value: str | None) -> None:
    try:
        parsed = parse_json_object(value)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValidationError("Resume content must be a valid JSON object.") from exc
    if not parsed:
        raise ValidationError("Resume content must include at least one section.")
