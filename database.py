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
    """Initializes schema including Albums support."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Assets Table
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
    
    # 2. Albums Table (New)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS albums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    # 3. Add album_id to assets (Migration logic)
    try:
        cursor.execute('ALTER TABLE gallery_assets ADD COLUMN album_id INTEGER REFERENCES albums(id)')
        print("ℹ️  Migrated DB: Added album_id to gallery_assets")
    except sqlite3.OperationalError:
        pass # Column likely exists

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_wp_id ON gallery_assets(wp_media_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_album_id ON gallery_assets(album_id);')
    
    conn.commit()
    conn.close()

def create_album(title):
    """Creates a new album and returns its ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    album_id = None
    try:
        cursor.execute('INSERT INTO albums (title) VALUES (?)', (title,))
        conn.commit()
        album_id = cursor.lastrowid
        
        if redis_client:
            redis_client.delete('gallery:albums') # Invalidate album cache
    except Exception as e:
        print(f"❌ Error creating album: {e}")
    finally:
        conn.close()
    return album_id

def get_albums():
    """Fetches all albums."""
    if redis_client:
        try:
            cached = redis_client.get('gallery:albums')
            if cached: return json.loads(cached)
        except: pass

    conn = get_db_connection()
    # Get albums with asset count and preview image
    query = '''
        SELECT a.id, a.title, a.created_at, COUNT(g.id) as asset_count, MIN(g.url_thumbnail) as preview_url
        FROM albums a
        LEFT JOIN gallery_assets g ON a.id = g.album_id
        GROUP BY a.id
        ORDER BY a.created_at DESC
    '''
    rows = conn.execute(query).fetchall()
    conn.close()
    
    albums = [dict(row) for row in rows]
    
    if redis_client:
        redis_client.setex('gallery:albums', 3600, json.dumps(albums))
        
    return albums

def get_assets_by_album(album_id):
    """Fetches assets for a specific album."""
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM gallery_assets WHERE album_id = ? ORDER BY created_at ASC', (album_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

def add_asset(asset_data, album_id=None):
    """Adds asset, optionally linked to an album."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO gallery_assets (
                wp_media_id, title, file_name, mime_type,
                url_full, url_thumbnail, url_medium, album_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            asset_data['wp_media_id'],
            asset_data['title'],
            asset_data['file_name'],
            asset_data['mime_type'],
            asset_data['url_full'],
            asset_data['url_thumbnail'],
            asset_data['url_medium'],
            album_id
        ))
        conn.commit()
        
        if redis_client:
            redis_client.delete('gallery:assets')
            if album_id:
                redis_client.delete('gallery:albums') # Update count/preview
                
    except sqlite3.IntegrityError as e:
        print(f"⚠️  Database Warning: Asset exists. ({e})")
    except Exception as e:
        print(f"❌ Database Error: {e}")
    finally:
        conn.close()

def get_all_assets(include_albums=False):
    """Retrieves standard assets (those NOT in an album) to keep main feed clean, OR all."""
    # Note: Logic changed to only show orphan assets in main feed if albums exist? 
    # For now, let's just get everything that IS NULL on album_id for the main "stream" 
    # OR we can show everything. Let's show "Recent Uploads" (all) for now.
    
    # Actually, user wants albums. Usually main feed = orphans + album folders.
    
    if redis_client:
        try:
            cached = redis_client.get('gallery:assets_main')
            if cached: return json.loads(cached)
        except: pass

    conn = get_db_connection()
    # Fetch assets that are NOT in an album (Orphans)
    rows = conn.execute('SELECT * FROM gallery_assets WHERE album_id IS NULL ORDER BY created_at DESC').fetchall()
    conn.close()
    
    assets = [dict(row) for row in rows]
    
    if redis_client:
        redis_client.setex('gallery:assets_main', 3600, json.dumps(assets))
            
    return assets
