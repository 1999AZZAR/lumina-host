from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from typing import Any

import redis

from config import get_config

_config = get_config()
DB_PATH = _config.db_path
logger = logging.getLogger(__name__)

ASSETS_CACHE_VERSION_KEY = 'lumina:assets:version'
ASSETS_CACHE_KEY_PREFIX = 'lumina:assets:'
ASSETS_CACHE_TTL = 300  # 5 minutes

redis_client: redis.Redis[str, str] | None = None
if _config.redis_url:
    try:
        redis_client = redis.from_url(_config.redis_url, decode_responses=True)
        redis_client.ping()
        logger.info("Redis connected: %s", _config.redis_url)
    except Exception as e:
        logger.warning("Redis configured but failed to connect: %s", e)
        redis_client = None


def _cache_version() -> str:
    if not redis_client:
        return '0'
    try:
        v = redis_client.get(ASSETS_CACHE_VERSION_KEY)
        return v or '0'
    except Exception:
        return '0'


def _invalidate_assets_cache() -> None:
    if redis_client:
        try:
            redis_client.incr(ASSETS_CACHE_VERSION_KEY)
        except Exception as e:
            logger.warning("Redis cache invalidation failed: %s", e)

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes the database schema if it doesn't exist."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                tenant_id INTEGER REFERENCES tenants(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1
            );
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token TEXT UNIQUE NOT NULL,
                name TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP
            );
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_api_tokens_user ON api_tokens(user_id);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_api_tokens_token ON api_tokens(token);')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gallery_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wp_media_id INTEGER UNIQUE NOT NULL,
                title TEXT NOT NULL,
                file_name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                url_full TEXT NOT NULL,
                url_thumbnail TEXT NOT NULL,
                url_medium TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cursor.execute('PRAGMA table_info(gallery_assets)')
        columns = [row[1] for row in cursor.fetchall()]
        if 'user_id' not in columns:
            cursor.execute('ALTER TABLE gallery_assets ADD COLUMN user_id INTEGER REFERENCES users(id)')
        if 'tenant_id' not in columns:
            cursor.execute('ALTER TABLE gallery_assets ADD COLUMN tenant_id INTEGER REFERENCES tenants(id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_wp_id ON gallery_assets(wp_media_id);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON gallery_assets(created_at);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_tenant ON gallery_assets(tenant_id);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_user ON gallery_assets(user_id);')
        conn.commit()

def add_asset(asset_data: dict[str, Any], user_id: int | None = None, tenant_id: int | None = None) -> None:
    """Adds a new asset to the local database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO gallery_assets (
                    wp_media_id, title, file_name, mime_type,
                    url_full, url_thumbnail, url_medium, user_id, tenant_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                asset_data['wp_media_id'],
                asset_data['title'],
                asset_data['file_name'],
                asset_data['mime_type'],
                asset_data['url_full'],
                asset_data['url_thumbnail'],
                asset_data['url_medium'],
                user_id,
                tenant_id,
            ))
            conn.commit()
            _invalidate_assets_cache()
        except sqlite3.IntegrityError as e:
            logger.warning("Asset with WP ID %s already exists: %s", asset_data['wp_media_id'], e)
        except Exception as e:
            logger.exception("Database error in add_asset: %s", e)

def get_assets(
    page: int = 1,
    per_page: int = 20,
    search_query: str | None = None,
    tenant_id: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """
    Retrieves assets with pagination and optional search.
    When tenant_id or user_id is set, only assets for that tenant/user are returned.
    Returns dict: {'assets': list, 'has_more': bool}
    Uses Redis cache when available; invalidate on add/delete.
    """
    qhash = hashlib.sha256((search_query or '').encode()).hexdigest()[:16]
    tid = tenant_id or 0
    uid = user_id or 0
    cache_key = f"{ASSETS_CACHE_KEY_PREFIX}{_cache_version()}:p{page}:q{qhash}:t{tid}:u{uid}"
    if redis_client:
        try:
            raw = redis_client.get(cache_key)
            if raw:
                data = json.loads(raw)
                return {'assets': data['assets'], 'has_more': data['has_more']}
        except Exception as e:
            logger.debug("Redis get failed: %s", e)

    offset = (page - 1) * per_page
    sql = 'SELECT * FROM gallery_assets'
    params: list = []
    conditions: list[str] = []
    if tenant_id is not None:
        conditions.append('tenant_id = ?')
        params.append(tenant_id)
    if user_id is not None:
        conditions.append('user_id = ?')
        params.append(user_id)
    if search_query:
        conditions.append("title LIKE ? ESCAPE '\\'")
        params.append(f'%{search_query}%')
    if conditions:
        sql += ' WHERE ' + ' AND '.join(conditions)
    sql += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page + 1, offset])

    with get_db_connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    assets = [dict(row) for row in rows]
    has_more = len(assets) > per_page
    if has_more:
        assets = assets[:per_page]
    result = {'assets': assets, 'has_more': has_more}
    if redis_client:
        try:
            redis_client.setex(
                cache_key,
                ASSETS_CACHE_TTL,
                json.dumps(result, default=str),
            )
        except Exception as e:
            logger.debug("Redis set failed: %s", e)
    return result

def delete_assets(
    asset_ids: list[int],
    tenant_id: int | None = None,
    user_id: int | None = None,
) -> list[int]:
    """
    Deletes assets from the local database by ID.
    When tenant_id or user_id is set, only deletes assets belonging to that tenant/user.
    Returns list of wp_media_id for remote cleanup.
    """
    if not asset_ids:
        return []
    placeholders = ','.join('?' * len(asset_ids))
    with get_db_connection() as conn:
        cursor = conn.cursor()
        sql = f'SELECT id, wp_media_id FROM gallery_assets WHERE id IN ({placeholders})'
        params: list = list(asset_ids)
        if tenant_id is not None:
            sql += ' AND tenant_id = ?'
            params.append(tenant_id)
        if user_id is not None:
            sql += ' AND user_id = ?'
            params.append(user_id)
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        allowed_ids = [row['id'] for row in rows]
        wp_ids = [row['wp_media_id'] for row in rows]
        if not allowed_ids:
            return []
        ph = ','.join('?' * len(allowed_ids))
        try:
            cursor.execute(f'DELETE FROM gallery_assets WHERE id IN ({ph})', allowed_ids)
            conn.commit()
            _invalidate_assets_cache()
        except Exception as e:
            logger.exception("Database error during delete: %s", e)
    return wp_ids


# --- Users ---

def create_user(
    username: str,
    email: str,
    password_hash: str,
    role: str = 'user',
    tenant_id: int | None = None,
) -> int | None:
    """Creates a user. Returns user id or None on conflict."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, role, tenant_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, email, password_hash, role, tenant_id))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    """Returns user row as dict or None."""
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT * FROM users WHERE id = ? AND is_active = 1',
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_username(username: str) -> dict[str, Any] | None:
    """Returns user row as dict or None."""
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT * FROM users WHERE username = ? AND is_active = 1',
            (username,),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str) -> dict[str, Any] | None:
    """Returns user row as dict or None."""
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT * FROM users WHERE email = ? AND is_active = 1',
            (email,),
        ).fetchone()
        return dict(row) if row else None


def list_users(tenant_id: int | None = None) -> list[dict[str, Any]]:
    """List users, optionally filtered by tenant_id."""
    with get_db_connection() as conn:
        if tenant_id is not None:
            rows = conn.execute(
                'SELECT * FROM users WHERE is_active = 1 AND tenant_id = ? ORDER BY username',
                (tenant_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM users WHERE is_active = 1 ORDER BY username',
            ).fetchall()
        return [dict(r) for r in rows]


# --- Tenants ---

def create_tenant(name: str, slug: str) -> int | None:
    """Creates a tenant. Returns tenant id or None on conflict."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO tenants (name, slug) VALUES (?, ?)',
                (name, slug),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_tenant_by_id(tenant_id: int) -> dict[str, Any] | None:
    with get_db_connection() as conn:
        row = conn.execute('SELECT * FROM tenants WHERE id = ?', (tenant_id,)).fetchone()
        return dict(row) if row else None


def get_tenant_by_slug(slug: str) -> dict[str, Any] | None:
    with get_db_connection() as conn:
        row = conn.execute('SELECT * FROM tenants WHERE slug = ?', (slug,)).fetchone()
        return dict(row) if row else None


# --- API tokens ---

def create_api_token(
    user_id: int,
    token: str,
    name: str | None = None,
    expires_at: str | None = None,
) -> int | None:
    """Creates an API token. Returns token id or None."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO api_tokens (user_id, token, name, expires_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, token, name, expires_at))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_api_token(token: str) -> dict[str, Any] | None:
    """Returns token row with user_id if valid and not expired."""
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT * FROM api_tokens WHERE token = ?',
            (token,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get('expires_at'):
            from datetime import datetime, timezone
            try:
                raw = d['expires_at'].replace('Z', '+00:00').replace(' ', 'T')
                exp = datetime.fromisoformat(raw)
                if not exp.tzinfo:
                    exp = exp.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) >= exp:
                    return None
            except Exception:
                pass
        return d


def revoke_api_token(token_id: int, user_id: int) -> bool:
    """Revokes a token if it belongs to user_id. Returns True if deleted."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM api_tokens WHERE id = ? AND user_id = ?', (token_id, user_id))
        conn.commit()
        return cursor.rowcount > 0


def get_user_tokens(user_id: int) -> list[dict[str, Any]]:
    """Returns list of token rows for the user (without token value)."""
    with get_db_connection() as conn:
        rows = conn.execute(
            'SELECT id, user_id, name, expires_at, created_at, last_used_at FROM api_tokens WHERE user_id = ?',
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def touch_api_token(token: str) -> None:
    """Update last_used_at for the token."""
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE api_tokens SET last_used_at = CURRENT_TIMESTAMP WHERE token = ?",
            (token,),
        )
        conn.commit()