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
        # Test connection
        redis_client.ping()
        print(f"✅ Redis connected: {REDIS_URL}")
    except Exception as e:
        print(f"⚠️  Redis configured but failed to connect: {e}")
        redis_client = None

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema if it doesn't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Schema from design.md
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
    
    conn.commit()
    conn.close()

def add_asset(asset_data):
    """
    Adds a new asset to the local database and invalidates cache.
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
        
        # Invalidate Cache
        if redis_client:
            try:
                redis_client.delete('gallery:assets')
            except Exception as e:
                print(f"⚠️  Failed to invalidate Redis cache: {e}")
                
    except sqlite3.IntegrityError as e:
        print(f"⚠️  Database Warning: Asset with WP ID {asset_data['wp_media_id']} already exists. ({e})")
    except Exception as e:
        print(f"❌ Database Error: {e}")
    finally:
        conn.close()

def get_all_assets():
    """Retrieves all assets, preferring Redis cache over SQLite."""
    
    # 1. Try Cache
    if redis_client:
        try:
            cached_data = redis_client.get('gallery:assets')
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            print(f"⚠️  Redis read error: {e}")

    # 2. Cache Miss - Query DB
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM gallery_assets ORDER BY created_at DESC').fetchall()
    conn.close()
    
    # Convert sqlite.Row to dicts for JSON serialization
    assets = [dict(row) for row in rows]
    
    # 3. Update Cache (TTL: 1 hour)
    if redis_client:
        try:
            redis_client.setex('gallery:assets', 3600, json.dumps(assets))
        except Exception as e:
            print(f"⚠️  Redis write error: {e}")
            
    return assets