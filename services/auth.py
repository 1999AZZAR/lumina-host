"""Authentication service: credentials, passwords, API tokens."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

import database


def hash_password(password: str) -> str:
    """Return a secure hash of the password."""
    return generate_password_hash(password, method="scrypt")


def verify_password(password_hash: str, password: str) -> bool:
    """Return True if password matches the stored hash."""
    return check_password_hash(password_hash, password)


def authenticate_user(username: str, password: str) -> dict | None:
    """
    Verify credentials. Returns user dict if valid, None otherwise.
    """
    user = database.get_user_by_username(username)
    if not user or not verify_password(user["password_hash"], password):
        return None
    return user


def create_user(
    username: str,
    email: str,
    password: str,
    role: str = "user",
    tenant_id: int | None = None,
) -> int | None:
    """
    Create a user with hashed password. Returns user id or None on conflict.
    """
    password_hash = hash_password(password)
    return database.create_user(username, email, password_hash, role, tenant_id)


def generate_api_token(
    user_id: int,
    name: str | None = None,
    expires_days: int | None = None,
) -> tuple[str, int]:
    """
    Create a new API token. Returns (raw_token, token_id).
    Raw token is shown only once; store hashed or discard after showing to user.
    """
    raw = secrets.token_urlsafe(32)
    expires_at = None
    if expires_days is not None and expires_days > 0:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()
    token_id = database.create_api_token(user_id, raw, name, expires_at)
    if not token_id:
        raise ValueError("Failed to create API token")
    return raw, token_id


def validate_api_token(token: str) -> dict | None:
    """
    Validate API token. Returns token row (with user_id) if valid and not expired, else None.
    """
    row = database.get_api_token(token)
    if not row:
        return None
    return row
