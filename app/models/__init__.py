from __future__ import annotations

from .activity import ActivityLog
from .analytics import AnalyticsHistory, ResumeScore
from .job import Job, JobMatch
from .payment import Payment
from .resume import Resume, ResumeSection, ResumeVersion
from .subscription import Subscription
from .user import User


def import_models() -> tuple[type, ...]:
    return (
        User,
        Resume,
        ResumeVersion,
        ResumeSection,
        Job,
        ResumeScore,
        JobMatch,
        AnalyticsHistory,
        ActivityLog,
        Subscription,
        Payment,
    )


__all__ = [
    "ActivityLog",
    "AnalyticsHistory",
    "Job",
    "JobMatch",
    "Payment",
    "Resume",
    "ResumeScore",
    "ResumeSection",
    "ResumeVersion",
    "Subscription",
    "User",
    "import_models",
]
