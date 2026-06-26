from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from flask import abort, jsonify, request
from flask_login import current_user, login_required

from app.models.user import User


F = TypeVar("F", bound=Callable[..., Any])


def role_required(*roles: str, allow_admin: bool = True) -> Callable[[F], F]:
    allowed_roles = set(roles)

    def decorator(view: F) -> F:
        @wraps(view)
        @login_required
        def wrapped(*args: Any, **kwargs: Any):
            if not _account_allowed():
                return _forbidden("Your account is not allowed to access this resource.")

            user_role = getattr(current_user, "role", None)
            if allow_admin and user_role == User.ROLE_ADMIN:
                return view(*args, **kwargs)
            if user_role not in allowed_roles:
                return _forbidden("You do not have permission to access this resource.")
            return view(*args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator


def active_user_required(view: F) -> F:
    @wraps(view)
    @login_required
    def wrapped(*args: Any, **kwargs: Any):
        if not _account_allowed():
            return _forbidden("Your account is not allowed to access this resource.")
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]


def verified_email_required(view: F) -> F:
    @wraps(view)
    @login_required
    def wrapped(*args: Any, **kwargs: Any):
        if not _account_allowed(require_verified=True):
            return _forbidden("Please verify your email address before continuing.")
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]


def user_required(view: F) -> F:
    return active_user_required(view)


def recruiter_required(view: F) -> F:
    return role_required(User.ROLE_RECRUITER, allow_admin=True)(view)


def admin_required(view: F) -> F:
    return role_required(User.ROLE_ADMIN, allow_admin=False)(view)


def owner_required(
    loader: Callable[..., Any],
    *,
    owner_attr: str = "user_id",
    allow_admin: bool = True,
) -> Callable[[F], F]:
    def decorator(view: F) -> F:
        @wraps(view)
        @login_required
        def wrapped(*args: Any, **kwargs: Any):
            if not _account_allowed(require_verified=True):
                return _forbidden("Your account is not allowed to access this resource.")

            resource = loader(*args, **kwargs)
            if resource is None:
                abort(404)

            owner_id = getattr(resource, owner_attr, None)
            if owner_id == current_user.id:
                return view(*args, **kwargs)
            if allow_admin and getattr(current_user, "role", None) == User.ROLE_ADMIN:
                return view(*args, **kwargs)
            return _forbidden("You do not have permission to access this resource.")

        return wrapped  # type: ignore[return-value]

    return decorator


def _account_allowed(*, require_verified: bool = True) -> bool:
    if not getattr(current_user, "is_authenticated", False):
        return False
    if getattr(current_user, "account_status", None) != User.STATUS_ACTIVE:
        return False
    if require_verified and not getattr(current_user, "is_email_verified", False):
        return False
    return True


def _forbidden(message: str):
    if _wants_json():
        return jsonify({"error": {"code": 403, "message": message}}), 403
    abort(403, description=message)


def _wants_json() -> bool:
    if request.path.startswith("/api/"):
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] >= request.accept_mimetypes["text/html"]
