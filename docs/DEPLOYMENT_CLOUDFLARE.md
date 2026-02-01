# 📦 Lumina-Host Deployment (Cloudflare Tunnel)

This guide covers deploying Lumina-Host using Docker behind a **Cloudflare Tunnel** for a secure, HTTPS-enabled setup with zero public ports exposed.

---

## 💡 Prerequisites

✔️ Linux Instance (e.g., OCI Ubuntu)
✔️ Docker & Docker Compose installed
✔️ Domain added to Cloudflare
✔️ Cloudflare Tunnel configured on the host

---

## 🗂️ Directory Setup

```sh
# Pick a directory
mkdir ~/lumina-host
cd ~/lumina-host

# Clone the repo
git clone https://github.com/1999AZZAR/lumina-host.git .
```

---

## 📄 Environment Variables

Lumina-Host expects a `.env` file. Use the provided example:

```sh
cp example.env .env
```

Edit `.env` with production values:

```env
FLASK_SECRET_KEY=<strong-secret>
ADMIN_USERNAME=<admin-user>
ADMIN_EMAIL=<admin-email>
ADMIN_PASSWORD=<admin-pass>
WP_API_URL=<wordpress-media-rest-url>
WP_USER=<wp-user>
WP_PASS=<wp-app-password>
DEBUG=0
```

> **Note:** If you don't use WordPress yet, leave the `WP_*` variables empty to use Mock Mode.

---

## 🐳 Docker Setup

The repository contains a `docker-compose.yml` configured for production.

### 👇 Build & Run

```sh
docker compose up -d --build
```

This starts:
*   **Flask App:** Running via Gunicorn (4 workers).
*   **Redis:** For rate limiting and caching.
*   **Persistence:** SQLite database stored in a named volume.

---

## 📍 Internal Port

The app, inside Docker, listens on port `5050`. To maintain security, we ensure it is only accessible via the Cloudflare Tunnel.

---

## 🔐 Cloudflare Tunnel Configuration

Point your Cloudflare Tunnel to the local Docker service.

### 🧾 `config.yml` (Example)

```yaml
tunnel: <tunnel-id>
credentials-file: /home/ubuntu/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: gallery.yourdomain.com
    service: http://127.0.0.1:5050
  - service: http_status:404
```

**Note:** We point to `127.0.0.1:5050` because Docker maps the port to the host's loopback interface.

---

## 📌 Verify Host Binding

Ensure Docker published the port only to localhost:

```sh
ss -ltn | grep 5050
```

You should see: `127.0.0.1:5050`.

---

## 🚀 Testing

### 🧪 Tunnel logs
```sh
journalctl -u cloudflared -f
```

### 🌐 Visit the app
Navigate to your configured hostname (e.g., `https://gallery.yourdomain.com`). It should load the Lumina Host gallery over HTTPS.

---

## ⚠️ Notes & Tips

### 🛡️ Cookies & HTTPS
With `DEBUG=0`, `SESSION_COOKIE_SECURE` is enforced. This requires HTTPS (provided by Cloudflare) to maintain your login session.

### 🗂️ Database Backup
The SQLite database is in a Docker volume. Back it up regularly:
```sh
docker cp $(docker compose ps -q web):/app/data/gallery.db ~/gallery-db-backup.db
```

---

## 📌 Troubleshooting

| Issue | Fix |
| :--- | :--- |
| **Blank page** | Check container logs: `docker compose logs -f web` |
| **Tunnel errors** | Check tunnel status: `systemctl status cloudflared` |
| **App not loading** | Confirm `127.0.0.1:5050` is reachable locally: `curl -I http://127.0.0.1:5050` |
