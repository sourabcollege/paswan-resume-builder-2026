from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional


EXPERIENCE_CHOICES = [
    ("", "Any experience"),
    ("entry", "Entry"),
    ("junior", "Junior"),
    ("mid", "Mid"),
    ("senior", "Senior"),
    ("lead", "Lead"),
    ("executive", "Executive"),
]
WORKPLACE_CHOICES = [("", "Any workplace"), ("onsite", "On-site"), ("remote", "Remote"), ("hybrid", "Hybrid")]
EMPLOYMENT_CHOICES = [
    ("", "Any employment"),
    ("full_time", "Full-time"),
    ("part_time", "Part-time"),
    ("contract", "Contract"),
    ("internship", "Internship"),
    ("freelance", "Freelance"),
]


def _strip(value: str | None) -> str:
    return (value or "").strip()


class JobSearchForm(FlaskForm):
    class Meta:
        csrf = False

    q = StringField("Search", filters=[_strip], validators=[Optional(), Length(max=180)])
    location = StringField("Location", filters=[_strip], validators=[Optional(), Length(max=180)])
    experience_level = SelectField("Experience", choices=EXPERIENCE_CHOICES, validators=[Optional()])
    workplace_type = SelectField("Workplace", choices=WORKPLACE_CHOICES, validators=[Optional()])
    employment_type = SelectField("Employment", choices=EMPLOYMENT_CHOICES, validators=[Optional()])
    limit = StringField("Limit", filters=[_strip], validators=[Optional(), Length(max=3)])
    offset = StringField("Offset", filters=[_strip], validators=[Optional(), Length(max=8)])


class JobRecommendationForm(FlaskForm):
    class Meta:
        csrf = False

    resume_id = StringField("Resume", filters=[_strip], validators=[DataRequired(), Length(min=36, max=36)])
    version_id = StringField("Version", filters=[_strip], validators=[Optional(), Length(min=36, max=36)])


class JobMatchForm(FlaskForm):
    resume_id = StringField("Resume", filters=[_strip], validators=[DataRequired(), Length(min=36, max=36)])
    version_id = StringField("Version", filters=[_strip], validators=[Optional(), Length(min=36, max=36)])
    submit = SubmitField("Calculate match")


class JobApplyForm(FlaskForm):
    resume_id = StringField("Resume", filters=[_strip], validators=[DataRequired(), Length(min=36, max=36)])
    version_id = StringField("Version", filters=[_strip], validators=[Optional(), Length(min=36, max=36)])
    submit = SubmitField("Track application")


class JobTrackingForm(FlaskForm):
    resume_id = StringField("Resume", filters=[_strip], validators=[DataRequired(), Length(min=36, max=36)])
    version_id = StringField("Version", filters=[_strip], validators=[Optional(), Length(min=36, max=36)])
    status = SelectField(
        "Status",
        choices=[("saved", "Saved"), ("applied", "Applied"), ("hidden", "Hidden")],
        validators=[DataRequired()],
    )
    submit = SubmitField("Update tracking")
