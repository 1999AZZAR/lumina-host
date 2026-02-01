#!/usr/bin/env python3
"""
Migration: add user system (AMT).
- Ensures tenants, users, api_tokens tables and gallery_assets.user_id/tenant_id exist.
- Creates default tenant and admin user if missing.
- Assigns existing gallery_assets to default admin/tenant.
Run from project root: python -m migrations.add_user_system
"""

from __future__ import annotations

import os
import sys

# Project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import database
from config import get_config
from services.auth import hash_password

_config = get_config()


def main() -> None:
    database.init_db()

    with database.get_db_connection() as conn:
        cursor = conn.cursor()

        # Default tenant
        cursor.execute("SELECT id FROM tenants LIMIT 1")
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO tenants (name, slug) VALUES (?, ?)", ("Default", "default"))
            conn.commit()
            tenant_id = cursor.lastrowid
            print(f"Created default tenant (id={tenant_id})")
        else:
            tenant_id = row["id"]
            print(f"Using existing tenant id={tenant_id}")

        # Default admin user
        admin_username = os.getenv("ADMIN_USERNAME", "admin").strip()
        admin_email = os.getenv("ADMIN_EMAIL", "admin@localhost").strip()
        admin_password = (os.getenv("ADMIN_PASSWORD") or "").strip()

        cursor.execute("SELECT id FROM users WHERE role = 'admin' AND is_active = 1 LIMIT 1")
        row = cursor.fetchone()
        if not row:
            if not admin_password:
                if sys.stdin.isatty():
                    import getpass
                    admin_password = getpass.getpass(f"Set password for admin user '{admin_username}': ")
                
                if not admin_password:
                    print("Skipping admin creation: ADMIN_PASSWORD not set and not interactive.")
                    return # Exit migration without error, admin can be created later or via env var restart

            password_hash = hash_password(admin_password)
            cursor.execute(
                "INSERT INTO users (username, email, password_hash, role, tenant_id) VALUES (?, ?, ?, ?, ?)",
                (admin_username, admin_email, password_hash, "admin", tenant_id),
            )
            conn.commit()
            admin_id = cursor.lastrowid
            print(f"Created admin user '{admin_username}' (id={admin_id})")
        else:
            admin_id = row["id"]
            print(f"Using existing admin user id={admin_id}")
            # If ADMIN_PASSWORD is set, update admin password so login matches .env
            if admin_password:
                password_hash = hash_password(admin_password)
                cursor.execute(
                    "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (password_hash, admin_id),
                )
                conn.commit()
                print(f"Updated password for admin user '{admin_username}' from ADMIN_PASSWORD.")

        # Assign existing assets to default admin/tenant
        cursor.execute(
            "UPDATE gallery_assets SET user_id = ?, tenant_id = ? WHERE user_id IS NULL",
            (admin_id, tenant_id),
        )
        updated = cursor.rowcount
        conn.commit()
        if updated:
            print(f"Assigned {updated} existing assets to default admin/tenant.")
        else:
            print("No unassigned assets to update.")

    print("Migration complete.")


if __name__ == "__main__":
    main()
