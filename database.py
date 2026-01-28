import sqlite3
import os
import json
import redis
from datetime import datetime

DB_PATH = 'gallery.db'

# --- Redis Configuration (Optional) ---
REDIS_URL = os.getenv('REDIS_URL')
redis_client = None

if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        print(f"✅ Redis connected: {REDIS_URL}")
    except Exception as e:
        print(f"⚠️  Redis configured but failed to connect: {e}")
        redis_client = None

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema if it doesn't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Original Schema
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
    conn.close()

def add_asset(asset_data):
    """
    Adds a new asset to the local database.
    """
    conn = get_db_connection()
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
        # Note: We removed global cache invalidation for scalability.
        # Pagination prevents caching the entire list effectively without complex keys.
                
    except sqlite3.IntegrityError as e:
        print(f"⚠️  Database Warning: Asset with WP ID {asset_data['wp_media_id']} already exists. ({e})")
    except Exception as e:
        print(f"❌ Database Error: {e}")
    finally:
        conn.close()

def get_assets(page=1, per_page=20, search_query=None):
    """
    Retrieves assets with pagination and optional search.
    Args:
        page (int): Page number (1-based).
        per_page (int): Items per page.
        search_query (str): Optional search term for title.
    Returns:
        dict: {'assets': list, 'has_more': bool}
    """
    conn = get_db_connection()
    offset = (page - 1) * per_page
    
    # Base Query
    sql = 'SELECT * FROM gallery_assets'
    params = []
    
    # Search Filter
    if search_query:
        sql += ' WHERE title LIKE ?'
        params.append(f'%{search_query}%')
    
    # Order & Pagination
    sql += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page + 1, offset]) # Fetch one extra to check 'has_more'
    
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    
    assets = [dict(row) for row in rows]
    has_more = False
    
    if len(assets) > per_page:
        has_more = True
        assets = assets[:per_page] # Trim the extra one
        
    return {'assets': assets, 'has_more': has_more}

def delete_assets(asset_ids):
    """Deletes assets from the local database by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    placeholders = ','.join('?' * len(asset_ids))
    cursor.execute(f'SELECT wp_media_id FROM gallery_assets WHERE id IN ({placeholders})', asset_ids)
    wp_ids = [row['wp_media_id'] for row in cursor.fetchall()]
    
    try:
        cursor.execute(f'DELETE FROM gallery_assets WHERE id IN ({placeholders})', asset_ids)
        conn.commit()
    except Exception as e:
        print(f"❌ Database Error during delete: {e}")
    finally:
        conn.close()
        
    return wp_ids