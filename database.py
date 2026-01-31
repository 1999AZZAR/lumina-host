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
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_wp_id ON gallery_assets(wp_media_id);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON gallery_assets(created_at);')
        conn.commit()

def add_asset(asset_data: dict[str, Any]) -> None:
    """Adds a new asset to the local database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO gallery_assets (
                    wp_media_id, title, file_name, mime_type,
                    url_full, url_thumbnail, url_medium
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                asset_data['wp_media_id'],
                asset_data['title'],
                asset_data['file_name'],
                asset_data['mime_type'],
                asset_data['url_full'],
                asset_data['url_thumbnail'],
                asset_data['url_medium']
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
) -> dict[str, Any]:
    """
    Retrieves assets with pagination and optional search.
    Returns dict: {'assets': list, 'has_more': bool}
    Uses Redis cache when available; invalidate on add/delete.
    """
    qhash = hashlib.sha256((search_query or '').encode()).hexdigest()[:16]
    cache_key = f"{ASSETS_CACHE_KEY_PREFIX}{_cache_version()}:p{page}:q{qhash}"
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
    if search_query:
        sql += " WHERE title LIKE ? ESCAPE '\\'"
        params.append(f'%{search_query}%')
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

def delete_assets(asset_ids: list[int]) -> list[int]:
    """Deletes assets from the local database by ID. Returns list of wp_media_id for remote cleanup."""
    if not asset_ids:
        return []
    placeholders = ','.join('?' * len(asset_ids))
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f'SELECT wp_media_id FROM gallery_assets WHERE id IN ({placeholders})', asset_ids)
        wp_ids = [row['wp_media_id'] for row in cursor.fetchall()]
        try:
            cursor.execute(f'DELETE FROM gallery_assets WHERE id IN ({placeholders})', asset_ids)
            conn.commit()
            _invalidate_assets_cache()
        except Exception as e:
            logger.exception("Database error during delete: %s", e)
    return wp_ids