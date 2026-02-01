# Cloudflare Tunnel Deployment Guide

This guide details the production-grade deployment of Lumina Host on an OCI (Oracle Cloud Infrastructure) instance (or any Linux server) using **Docker** and **Cloudflare Tunnel**.

## Architecture

This setup ensures maximum security by keeping all ports closed to the public internet.

```
Internet
  ↓ (HTTPS)
Cloudflare (WAF, CDN, DDoS Protection)
  ↓ (Encrypted Tunnel)
cloudflared (Running on Host)
  ↓ (http://127.0.0.1:5050)
Docker Container (Lumina Host / Gunicorn)
```

**Key Benefits:**
*   **Zero Open Ports:** No need to open port 80, 443, or 5050 on your firewall/VCN.
*   **Secure:** Traffic is encrypted from Cloudflare to your server.
*   **Isolated:** Docker listens only on localhost.

---

## 1. Prepare the Application

First, set up the application using Docker.

1.  **Clone the Repository**
    ```bash
    mkdir -p ~/lumina-host
    cd ~/lumina-host
    git clone https://github.com/1999AZZAR/lumina-host.git .
    ```

2.  **Configure Environment**
    ```bash
    cp example.env .env
    ```
    Edit `.env` with your credentials:
    ```ini
    FLASK_SECRET_KEY=<generate_strong_secret>
    DEBUG=0  # Critical: Enforces secure cookies
    
    # Admin Credentials
    ADMIN_USERNAME=admin
    ADMIN_EMAIL=admin@example.com
    ADMIN_PASSWORD=<strong_password>

    # WordPress (Optional)
    WP_API_URL=https://your-wp-site.com/wp-json/wp/v2/media
    WP_USER=lumina_bot
    WP_PASS=xxxx xxxx xxxx xxxx
    ```

3.  **Start Docker Containers**
    ```bash
    docker compose up -d --build
    ```

4.  **Verify Localhost Binding**
    Ensure the app is running and listening **only** on localhost.
    ```bash
    ss -ltn | grep 5050
    ```
    **Expected Output:** `127.0.0.1:5050` (It must *not* be `0.0.0.0:5050` or `*:5050` exposed publicly).

---

## 2. Install & Configure Cloudflare Tunnel

We will use the host-based `cloudflared` to route traffic to the Docker container.

### Step 2.1: Install `cloudflared`

**For Debian/Ubuntu (AMD64 & ARM64/Ampere):**

```bash
# Add Cloudflare GPG key
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null

# Add Repository
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared/ any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list

# Install
sudo apt-get update && sudo apt-get install cloudflared
```

Verify installation:
```bash
cloudflared --version
```

### Step 2.2: Authenticate

```bash
cloudflared tunnel login
```
*   Copy the URL provided into your browser.
*   Log in to Cloudflare and authorize the domain you want to use.

### Step 2.3: Create Tunnel

Create a new tunnel (e.g., named `lumina`).

```bash
cloudflared tunnel create lumina
```
**Output:** It will save a UUID (e.g., `b2181946-fb61...`) and a credentials file path. **Note this UUID.**

### Step 2.4: Route DNS

Map your domain (or subdomain) to this tunnel.

```bash
# Example: Using a subdomain
cloudflared tunnel route dns lumina gallery.yourdomain.com
```

### Step 2.5: Configure Ingress

Create the configuration file.

```bash
sudo mkdir -p /etc/cloudflared
sudo nano /etc/cloudflared/config.yml
```

Paste the following configuration (replace `<UUID>` and `hostname`):

```yaml
tunnel: <UUID>
credentials-file: /home/ubuntu/.cloudflared/<UUID>.json

ingress:
  # Map your domain to the local Docker port
  - hostname: gallery.yourdomain.com
    service: http://127.0.0.1:5050
  
  # Catch-all for unmatched requests
  - service: http_status:404
```

> **Note:** Ensure the `credentials-file` path matches where `cloudflared` saved the JSON file (usually `~/.cloudflared/`). If running as a system service, you might need to move the JSON file to `/etc/cloudflared/` or update the path.

### Step 2.6: Run as Service

Install `cloudflared` as a system service to ensure it starts on boot.

```bash
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

Check status:
```bash
sudo systemctl status cloudflared
```

---

## 3. Hardening & Best Practices

### 🛡️ Cloudflare Access (Recommended)
Since your app provides admin capabilities, add an extra layer of security:
1.  Go to **Cloudflare Dashboard > Zero Trust > Access**.
2.  Create an Application for `gallery.yourdomain.com`.
3.  Add a policy (e.g., "Allow emails ending in @yourdomain.com" or specific GitHub users).
4.  This adds a Cloudflare login screen *before* anyone hits your app.

### 🚫 Security Checklist
*   [ ] **Port 5050 is NOT open** on your OCI Security List / VCN.
*   [ ] **DEBUG=0** in `.env`.
*   [ ] **HTTPS Only:** Cloudflare handles SSL. Your app listens on HTTP locally, which is safe inside the tunnel.

---

## 4. Maintenance

### Backup Database
```bash
docker cp $(docker compose ps -q web):/app/data/gallery.db ./gallery-backup.db
```

### Update Application
```bash
git pull
docker compose up -d --build
```
