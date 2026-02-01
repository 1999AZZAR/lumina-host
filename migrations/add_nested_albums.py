#!/usr/bin/env python3
"""
Migration: add nested albums and album visibility.
- Adds parent_id to albums (self-reference).
- Adds is_public to albums.
Run from project root: python -m migrations.add_nested_albums
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
    print("Running migration: add_nested_albums")
    
    with database.get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('PRAGMA table_info(albums)')
        columns = [row[1] for row in cursor.fetchall()]
        
        # 1. Add parent_id
        if 'parent_id' not in columns:
            cursor.execute('ALTER TABLE albums ADD COLUMN parent_id INTEGER REFERENCES albums(id) ON DELETE SET NULL')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_albums_parent ON albums(parent_id);')
            print("Added parent_id to albums table.")
        else:
            print("albums already has parent_id column.")

        # 2. Add is_public
        if 'is_public' not in columns:
            cursor.execute('ALTER TABLE albums ADD COLUMN is_public INTEGER NOT NULL DEFAULT 1')
            print("Added is_public to albums table.")
        else:
            print("albums already has is_public column.")
            
        conn.commit()

    print("Migration complete.")


if __name__ == "__main__":
    main()
