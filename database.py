import sqlite3
import os
from datetime import datetime

DB_PATH = 'gallery.db'

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
    Adds a new asset to the local database.
    
    Args:
        asset_data (dict): Dictionary containing asset details:
                           wp_media_id, title, file_name, mime_type,
                           url_full, url_thumbnail, url_medium
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
    except sqlite3.IntegrityError as e:
        print(f"⚠️  Database Warning: Asset with WP ID {asset_data['wp_media_id']} already exists. ({e})")
    except Exception as e:
        print(f"❌ Database Error: {e}")
    finally:
        conn.close()

def get_all_assets():
    """Retrieves all assets ordered by creation date (newest first)."""
    conn = get_db_connection()
    assets = conn.execute('SELECT * FROM gallery_assets ORDER BY created_at DESC').fetchall()
    conn.close()
    return assets
