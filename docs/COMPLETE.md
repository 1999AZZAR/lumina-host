# Complete Guide

## Overview

Lumina Host is a decoupled image gallery: Flask serves the UI and API, SQLite caches asset metadata, and WordPress (optional) stores and serves media. AMT (Authentication, Authorization, Multi-Tenancy) adds users, roles, tenant isolation, and API tokens.

## Features

* **Gallery** – Browse, search, upload, and delete assets. Infinite scroll and bulk actions (download, delete).
* **WordPress integration** – Media is uploaded to and deleted from WordPress when configured; otherwise mock mode is used.
* **AMT** – Login, registration (optional), profile, API tokens. Admins see all assets; other users see only their tenant/user assets. Upload and delete require authentication.
* **Security** – CSRF protection, rate limits, session cookie hardening, API token hashing, input validation.

## User flows

* **Guest** – Can browse the gallery and use search. Upload and delete are hidden; attempting them returns 401.
* **Login** – POST /login with username and password. Redirect to gallery or `next` URL.
* **Logout** – POST /logout (form with CSRF). GET /logout redirects to index.
* **Register** – Only when ENABLE_REGISTRATION=1. Username (alphanumeric + underscore), email, password (min 8 chars, one letter and one digit).
* **Profile** – View username/email/role; create and revoke API tokens. Tokens are shown once; store securely.
* **Upload** – Select or drag files; uploads are tied to the current user and tenant.
* **Delete** – Select assets, then delete. Only assets belonging to the current tenant/user (or any for admin) are removed.
* **Admin** – Admin users can open /admin/users to list, create, and deactivate users.

## Configuration

Environment variables (see project root `example.env` and README):

| Category | Variables | Notes |
|----------|-----------|-------|
| Flask | FLASK_SECRET_KEY | Required in production. |
| WordPress | WP_API_URL, WP_USER, WP_PASS | Optional; omit for mock mode. |
| Redis | REDIS_URL, RATELIMIT_STORAGE_URL | REDIS_URL: optional cache. RATELIMIT_STORAGE_URL: optional; use in production for rate limits. |
| AMT | ENABLE_REGISTRATION, API_TOKEN_EXPIRY_DAYS, ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD | Default admin is created at startup when ADMIN_PASSWORD is set. Username and email must be valid (alphanumeric/underscore username, valid or @localhost email). |

**Production:** Use HTTPS, set SESSION_COOKIE_SECURE (automatic when not debug), set RATELIMIT_STORAGE_URL to Redis, and use a strong ADMIN_PASSWORD.

## Architecture (short)

* **Flask** – Web app and API; Flask-Login for sessions; Flask-Limiter for rate limits; Flask-WTF for CSRF.
* **SQLite** – Tables: tenants, users, api_tokens, gallery_assets. Assets are keyed by wp_media_id and optionally user_id/tenant_id.
* **Redis** – Optional: cache for asset list, optional storage for rate limits.
* **WordPress REST API** – Optional: upload and delete media; proxy_download whitelists the same host for CORS-safe download.

For full API details, see [API.md](API.md). For WordPress setup, see [WORDPRESS_SETUP.md](WORDPRESS_SETUP.md).
