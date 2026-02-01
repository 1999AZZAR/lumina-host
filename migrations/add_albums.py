#!/usr/bin/env python3
"""
Migration: add albums support.
- Creates albums table.
- Adds album_id to gallery_assets.
Run from project root: python -m migrations.add_albums
"""

from __future__ import annotations

import os
import sys
import sqlite3

# Project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import database
from config import get_config

_config = get_config()


def main() -> None:
    print("Running migration: add_albums")
    
    with database.get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Check if albums table exists and has correct schema
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='albums'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(albums)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'user_id' not in cols or 'name' not in cols:
                print("Detected invalid/old albums table. Dropping and recreating...")
                cursor.execute("DROP TABLE albums")
        
        # 1. Create albums table
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
        print("Created/Checked albums table.")

        # 2. Add album_id to gallery_assets
        cursor.execute('PRAGMA table_info(gallery_assets)')
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'album_id' not in columns:
            cursor.execute('ALTER TABLE gallery_assets ADD COLUMN album_id INTEGER REFERENCES albums(id) ON DELETE SET NULL')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_album ON gallery_assets(album_id);')
            print("Added album_id to gallery_assets table.")
        else:
            print("gallery_assets already has album_id column.")
            
        conn.commit()

    print("Migration complete.")


if __name__ == "__main__":
    main()
