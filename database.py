from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from typing import Any

def _token_hash(raw: str) -> str:
    """SHA-256 hash of token for storage and lookup."""
    return hashlib.sha256(raw.encode()).hexdigest()

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
    conn.execute("PRAGMA foreign_keys = ON")
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
            CREATE TABLE IF NOT EXISTS albums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                user_id INTEGER REFERENCES users(id),
                tenant_id INTEGER REFERENCES tenants(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_albums_user ON albums(user_id);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_albums_tenant ON albums(tenant_id);')
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
        cursor.execute('PRAGMA table_info(api_tokens)')
        token_cols = [row[1] for row in cursor.fetchall()]
        if 'token_hash' not in token_cols:
            cursor.execute('ALTER TABLE api_tokens ADD COLUMN token_hash TEXT')
            conn.commit()
            cursor.execute('SELECT id, token FROM api_tokens WHERE token IS NOT NULL AND token != ""')
            for row in cursor.fetchall():
                th = _token_hash(row['token'])
                cursor.execute('UPDATE api_tokens SET token_hash = ? WHERE id = ?', (th, row['id']))
            conn.commit()
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_api_tokens_token_hash ON api_tokens(token_hash)')
            conn.commit()
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
                user_id INTEGER REFERENCES users(id),
                tenant_id INTEGER REFERENCES tenants(id),
                album_id INTEGER REFERENCES albums(id) ON DELETE SET NULL,
                is_public INTEGER NOT NULL DEFAULT 1,
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
        if 'album_id' not in columns:
            cursor.execute('ALTER TABLE gallery_assets ADD COLUMN album_id INTEGER REFERENCES albums(id) ON DELETE SET NULL')
        if 'is_public' not in columns:
            cursor.execute('ALTER TABLE gallery_assets ADD COLUMN is_public INTEGER NOT NULL DEFAULT 1')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_wp_id ON gallery_assets(wp_media_id);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON gallery_assets(created_at);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_tenant ON gallery_assets(tenant_id);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_user ON gallery_assets(user_id);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_album ON gallery_assets(album_id);')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        ''')
        conn.commit()

def add_asset(asset_data: dict[str, Any], user_id: int | None = None, tenant_id: int | None = None, album_id: int | None = None) -> None:
    """Adds a new asset to the local database. New assets are public by default."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO gallery_assets (
                    wp_media_id, title, file_name, mime_type,
                    url_full, url_thumbnail, url_medium, user_id, tenant_id, album_id, is_public
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
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
                album_id,
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
    album_id: int | None = None,
    public_only: bool = False,
) -> dict[str, Any]:
    """
    Retrieves assets with pagination and optional search.
    When tenant_id or user_id is set, only assets for that tenant/user are returned.
    When public_only is True, only assets with is_public=1 are returned (for public view).
    Returns dict: {'assets': list, 'has_more': bool}
    Uses Redis cache when available; invalidate on add/delete.
    """
    qhash = hashlib.sha256((search_query or '').encode()).hexdigest()[:16]
    tid = tenant_id or 0
    uid = user_id or 0
    aid = album_id or 0
    pub = 1 if public_only else 0
    cache_key = f"{ASSETS_CACHE_KEY_PREFIX}{_cache_version()}:p{page}:q{qhash}:t{tid}:u{uid}:a{aid}:pub{pub}"
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
    if album_id is not None:
        conditions.append('album_id = ?')
        params.append(album_id)
    if public_only:
        conditions.append('is_public = 1')
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


def update_asset_visibility(
    asset_id: int,
    is_public: bool,
    tenant_id: int | None = None,
    user_id: int | None = None,
) -> bool:
    """
    Update is_public for an asset. Only updates if the asset belongs to the given
    tenant/user, or if both are None (admin). Returns True if a row was updated.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        sql = 'UPDATE gallery_assets SET is_public = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
        params: list[Any] = [1 if is_public else 0, asset_id]
        if tenant_id is not None:
            sql += ' AND tenant_id = ?'
            params.append(tenant_id)
        if user_id is not None:
            sql += ' AND user_id = ?'
            params.append(user_id)
        cursor.execute(sql, tuple(params))
        conn.commit()
        _invalidate_assets_cache()
        return cursor.rowcount > 0


def move_assets_to_album(
    asset_ids: list[int],
    album_id: int | None,
    tenant_id: int | None = None,
    user_id: int | None = None,
) -> int:
    """
    Updates album_id for multiple assets.
    Checks tenant/user ownership.
    Returns number of updated rows.
    """
    if not asset_ids:
        return 0
    placeholders = ','.join('?' * len(asset_ids))
    with get_db_connection() as conn:
        cursor = conn.cursor()
        sql = f'UPDATE gallery_assets SET album_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})'
        params: list[Any] = [album_id] + list(asset_ids)
        
        if tenant_id is not None:
            sql += ' AND tenant_id = ?'
            params.append(tenant_id)
        if user_id is not None:
            sql += ' AND user_id = ?'
            params.append(user_id)
            
        cursor.execute(sql, tuple(params))
        conn.commit()
        _invalidate_assets_cache()
        return cursor.rowcount


def get_setting(key: str) -> str | None:
    """Return setting value by key, or None if not set."""
    with get_db_connection() as conn:
        row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        return row['value'] if row else None


def set_setting(key: str, value: str) -> None:
    """Set a setting (insert or replace)."""
    with get_db_connection() as conn:
        conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        conn.commit()


# --- Albums ---

def create_album(
    name: str,
    description: str | None = None,
    user_id: int | None = None,
    tenant_id: int | None = None,
) -> int | None:
    """Creates a new album. Returns album id."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO albums (name, description, user_id, tenant_id)
            VALUES (?, ?, ?, ?)
        ''', (name, description, user_id, tenant_id))
        conn.commit()
        return cursor.lastrowid


def get_album(album_id: int) -> dict[str, Any] | None:
    """Returns album row as dict or None."""
    with get_db_connection() as conn:
        row = conn.execute('SELECT * FROM albums WHERE id = ?', (album_id,)).fetchone()
        return dict(row) if row else None


def get_albums(
    tenant_id: int | None = None,
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    """Returns list of albums filtered by tenant/user."""
    sql = 'SELECT * FROM albums'
    params = []
    conditions = []
    if tenant_id is not None:
        conditions.append('tenant_id = ?')
        params.append(tenant_id)
    if user_id is not None:
        conditions.append('user_id = ?')
        params.append(user_id)
    
    if conditions:
        sql += ' WHERE ' + ' AND '.join(conditions)
    sql += ' ORDER BY created_at DESC'

    with get_db_connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]


def update_album(album_id: int, name: str, description: str | None = None) -> bool:
    """Updates album details."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE albums SET name = ?, description = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (name, description, album_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_album(album_id: int) -> bool:
    """Deletes an album. Associated assets will have album_id set to NULL (via ON DELETE SET NULL)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM albums WHERE id = ?', (album_id,))
        conn.commit()
        return cursor.rowcount > 0


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
    """Creates an API token. Stores hash only; token is raw (caller shows once). Returns token id or None."""
    th = _token_hash(token)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO api_tokens (user_id, token, token_hash, name, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, th, th, name, expires_at))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_api_token(token: str) -> dict[str, Any] | None:
    """Returns token row with user_id if valid and not expired. Lookup by token hash."""
    th = _token_hash(token)
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT * FROM api_tokens WHERE token_hash = ?',
            (th,),
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
    """Update last_used_at for the token. Lookup by token hash."""
    th = _token_hash(token)
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE api_tokens SET last_used_at = CURRENT_TIMESTAMP WHERE token_hash = ?",
            (th,),
        )
        conn.commit()