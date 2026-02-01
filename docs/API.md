# API Reference

## Authentication

Two methods are supported:

1. **Session (cookie)** – After `POST /login`, the session cookie is sent automatically. Use for browser-based access.
2. **Bearer token** – Send header `Authorization: Bearer <token>`. Tokens are created in Profile (GET /profile) via "Create token"; the raw token is shown once. Store it securely.

API endpoints that require auth return `401` when unauthenticated and `403` when forbidden.

---

## Endpoints

### Gallery and assets

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | No | Gallery page (HTML). Public view shows only public assets; when logged in, assets are filtered by tenant/user and include hidden; admins see all. |
| GET | `/api/assets` | No | List assets. Query: `page` (int, default 1), `q` (search). Public view returns only `is_public=1`; when logged in returns own assets (including hidden). Rate limit: 60/hour. |
| PATCH | `/api/assets/<id>/visibility` | Yes | Set visibility. JSON body: `{ "is_public": true|false }`. Owner or admin only. |
| POST | `/upload` | Yes | Upload one or more image files (multipart). **Note:** Images are automatically optimized (resized to max 2560px, compressed, EXIF stripped) and renamed (`MMDDYY_HHMM_WXYZ.ext`) before storage. Rate limit: 20/minute. |
| POST | `/delete` | Yes | Bulk delete. JSON body: `{ "ids": [1, 2, ...] }`. Only own tenant/user assets; admins can delete any. Rate limit: 30/minute. |
| GET | `/proxy_download?url=` | No | Proxy image download (URL must match WordPress host). Rate limit: 30/minute. |

### Auth (HTML + redirects)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET, POST | `/login` | No | Login page and handler. Rate limit: 10/minute. |
| GET, POST | `/logout` | No | POST performs logout; GET redirects to index. |
| GET, POST | `/register` | No | Registration (only when ENABLE_REGISTRATION=1). Rate limit: 5/minute. |
| GET | `/profile` | Yes | User profile and API token management. |

### API tokens

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/tokens` | Yes | List current user's tokens (no secret value). |
| POST | `/api/tokens` | Yes | Create token. JSON body (optional): `{ "name": "My token" }`. Returns `token` once. |
| DELETE | `/api/tokens/<id>` | Yes | Revoke token by id. |

### Admin (admin role only)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/admin/users` | Admin | List users. |
| POST | `/admin/users` | Admin | Create user. JSON: `username`, `email`, `password`, `role` (admin/user). Rate limit: 20/hour. |
| DELETE | `/admin/users/<user_id>` | Admin | Deactivate user (soft delete). |

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Health check. Returns JSON: `status`, `db`, `redis`. 503 if DB or Redis down. |

---

## Request / response examples

### GET /api/assets

```
GET /api/assets?page=1&q=photo
```

Response (200):

```json
{
  "assets": [
    {
      "id": 1,
      "wp_media_id": 123,
      "title": "020126_1630_abcd.jpg",
      "file_name": "020126_1630_abcd.jpg",
      "mime_type": "image/jpeg",
      "url_full": "https://...",
      "url_thumbnail": "https://...",
      "url_medium": "https://...",
      "created_at": "2025-01-01 12:00:00",
      "updated_at": "2025-01-01 12:00:00",
      "user_id": 1,
      "tenant_id": 1,
      "is_public": 1
    }
  ],
  "has_more": true
}
```

### PATCH /api/assets/<id>/visibility

```
PATCH /api/assets/1/visibility
Content-Type: application/json
X-CSRFToken: <csrf_token>
X-Requested-With: XMLHttpRequest

{ "is_public": false }
```

Response (200): `{ "id": 1, "is_public": false }`. Response (404): `{ "error": "Asset not found or access denied." }`.

### POST /delete

```
POST /delete
Content-Type: application/json
X-CSRFToken: <csrf_token>
X-Requested-With: XMLHttpRequest

{ "ids": [1, 2, 3] }
```

Response (200):

```json
{
  "message": "Deleted 3 local assets. Remote cleanup: 3/3 successful.",
  "deleted_ids": [1, 2, 3]
}
```

### POST /api/tokens

```
POST /api/tokens
Content-Type: application/json
X-CSRFToken: <csrf_token>
X-Requested-With: XMLHttpRequest

{ "name": "My API token" }
```

Response (201):

```json
{
  "id": 1,
  "token": "<raw_token_show_once>",
  "name": "My API token",
  "expires_days": 90,
  "message": "Store this token securely; it will not be shown again."
}
```

### GET /health

Response (200): `{ "status": "healthy", "db": "up", "redis": "up" }` or `"n/a"` for Redis when not configured.

Response (503): `{ "status": "unhealthy", "db": "down" }` or `{ "status": "degraded", "db": "up", "redis": "down" }`.

---

## Rate limits

Default (when no per-route limit): 200/day, 60/hour per IP.

| Route | Limit |
|-------|--------|
| /login | 10/minute |
| /register | 5/minute |
| /api/assets | 60/hour |
| /upload | 20/minute |
| /delete | 30/minute |
| /proxy_download | 30/minute |
| /admin/users (POST) | 20/hour |

In production, set `RATELIMIT_STORAGE_URI` (e.g. `redis://localhost:6379/0`) so limits are shared across processes.

---

## Error responses

JSON errors use body `{ "error": "<message>" }` when the request has `X-Requested-With: XMLHttpRequest`.

| Code | Meaning |
|------|--------|
| 400 | Bad request (validation, invalid id, missing body). |
| 401 | Authentication required. |
| 403 | Access denied (wrong role or tenant). |
| 404 | Resource not found (e.g. token or user). |
| 413 | Request entity too large (upload over max size). |
| 429 | Rate limit exceeded. |
| 500 | Internal server error. |
| 502/504 | Upstream error (WordPress failed to respond). |