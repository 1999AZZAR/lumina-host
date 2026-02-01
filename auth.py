"""Authorization decorators and current-user helpers for AMT."""

from __future__ import annotations

from functools import wraps

from flask import abort
from flask_login import UserMixin, current_user, login_required as flask_login_required


class User(UserMixin):
    """Flask-Login user wrapper around DB user row."""

    def __init__(self, row: dict):
        self.id = row["id"]
        self.username = row["username"]
        self.email = row.get("email", "")
        self.role = row.get("role", "user")
        self.tenant_id = row.get("tenant_id")
        self._active = bool(row.get("is_active", 1))

    @property
    def is_active(self) -> bool:
        return self._active

    def get_id(self) -> str:
        return str(self.id)


def get_current_user():
    """Return the current user object (Flask-Login) or None."""
    return current_user if current_user.is_authenticated else None


def get_current_tenant_id() -> int | None:
    """Return tenant_id for the current user, or None."""
    user = get_current_user()
    if not user:
        return None
    return getattr(user, "tenant_id", None)


def get_current_user_id() -> int | None:
    """Return user id for the current user, or None."""
    user = get_current_user()
    if not user:
        return None
    return getattr(user, "id", None)


def login_required(f):
    """Require authenticated user. Use with Flask-Login."""
    return flask_login_required(f)


def role_required(role: str):
    """Require the current user to have the given role (e.g. 'admin')."""

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            user_role = getattr(current_user, "role", None)
            if user_role != role:
                abort(403)
            return f(*args, **kwargs)

        return wrapped

    return decorator


def admin_required(f):
    """Require the current user to have role 'admin'."""
    return role_required("admin")(f)


def tenant_required(f):
    """
    Require the current user to have access to tenant data.
    Admins are allowed; other users must have a tenant_id.
    """
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if getattr(current_user, "role", None) == "admin":
            return f(*args, **kwargs)
        if getattr(current_user, "tenant_id", None) is None:
            abort(403)
        return f(*args, **kwargs)

    return wrapped
