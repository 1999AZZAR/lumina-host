"""Centralized configuration with validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    """Application configuration from environment."""

    # Flask
    secret_key: str = field(default_factory=lambda: os.getenv('FLASK_SECRET_KEY', '').strip())
    max_content_length_mb: int = 16
    debug: bool = field(
        default_factory=lambda: os.getenv('FLASK_ENV') == 'development'
        or os.getenv('DEBUG', '').lower() in ('1', 'true', 'yes')
    )

    # Database
    db_path: str = os.getenv('DB_PATH', 'gallery.db')

    # Redis (optional)
    redis_url: str | None = field(
        default_factory=lambda: (os.getenv('REDIS_URL') or '').strip() or None
    )

    # WordPress API (optional for mock mode)
    wp_api_url: str | None = field(
        default_factory=lambda: (os.getenv('WP_API_URL') or '').strip() or None
    )
    wp_user: str | None = field(
        default_factory=lambda: (os.getenv('WP_USER') or '').strip() or None
    )
    wp_pass: str | None = field(
        default_factory=lambda: (os.getenv('WP_PASS') or '').strip() or None
    )

    # Upload
    allowed_extensions: frozenset[str] = frozenset({'png', 'jpg', 'jpeg', 'gif', 'webp'})

    @property
    def max_content_length_bytes(self) -> int:
        return self.max_content_length_mb * 1024 * 1024

    @property
    def wp_configured(self) -> bool:
        return bool(self.wp_api_url and self.wp_user and self.wp_pass)


def resolve_secret_key(config: Config) -> str:
    """Resolve FLASK_SECRET_KEY; raise in production if missing."""
    if config.secret_key:
        return config.secret_key
    if config.debug:
        import secrets
        return secrets.token_hex(32)
    raise RuntimeError(
        'FLASK_SECRET_KEY must be set in environment. '
        'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
    )


def get_config() -> Config:
    """Return application config. Call after load_dotenv()."""
    return Config()
