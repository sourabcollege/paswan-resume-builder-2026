from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.mutable import MutableDict, MutableList

from app.extensions import db


JSONDict = MutableDict.as_mutable(db.JSON)
JSONList = MutableList.as_mutable(db.JSON)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def score_between_zero_and_hundred(column_name: str, constraint_name: str):
    return db.CheckConstraint(
        f"{column_name} IS NULL OR ({column_name} >= 0 AND {column_name} <= 100)",
        name=constraint_name,
    )


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
        index=True,
    )
