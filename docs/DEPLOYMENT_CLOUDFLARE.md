# Cloudflare Tunnel Deployment Guide

This guide details the deployment of Lumina Host using Docker and Cloudflare Tunnel. This configuration ensures the application remains isolated from the public internet, accessible only through a secure, encrypted tunnel.

## Prerequisites

*   Linux server (e.g., Ubuntu on OCI).
*   Docker and Docker Compose installed.
*   Active Cloudflare account with a domain.
*   Cloudflare Tunnel (`cloudflared`) installed and authenticated on the host.

## Installation

1.  **Prepare Directory**
    Create a directory and clone the repository.

    ```bash
    mkdir -p ~/lumina-host
    cd ~/lumina-host
    git clone https://github.com/1999AZZAR/lumina-host.git .
    ```

2.  **Install Cloudflared**
    Follow these steps to install the Cloudflare Tunnel client on Debian/Ubuntu.

    ```bash
    # Add Cloudflare gpg key
    sudo mkdir -p --mode=0755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null

    # Add Cloudflare apt repository
    echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared/ any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list

    # Install cloudflared
    sudo apt-get update && sudo apt-get install cloudflared
    ```

    **Authenticate Cloudflared**
    Authenticate the client with your Cloudflare account.

    ```bash
    cloudflared tunnel login
    ```

3.  **Configure Environment**
    Copy the example configuration.

    ```bash
    cp example.env .env
    ```

    Edit `.env` with production credentials. Ensure `DEBUG` is set to `0` to enforce secure cookies.

    ```ini
    # Security
    FLASK_SECRET_KEY=change_this_to_a_long_random_string
    DEBUG=0

    # Administrative Access
    ADMIN_USERNAME=admin
    ADMIN_EMAIL=admin@example.com
    ADMIN_PASSWORD=change_this_to_a_strong_password

    # WordPress Integration (Optional)
    WP_API_URL=https://your-wordpress-site.com/wp-json/wp/v2/media
    WP_USER=lumina_bot
    WP_PASS=xxxx xxxx xxxx xxxx
    ```

    **Security Warning:** Never commit `.env` to version control. It contains sensitive credentials.

4.  **Start Services**
    Build and start the containerized application.

    ```bash
    docker compose up -d --build
    ```

    This initializes:
    *   **Web Service:** Flask application running via Gunicorn (Production WSGI).
    *   **Redis:** For rate limiting and caching.
    *   **Data Volume:** Persistent storage for the SQLite database.

## Cloudflare Tunnel Configuration

Configure `cloudflared` to route traffic to the local Docker instance.

1.  **Locate Configuration**
    Edit your tunnel configuration file (typically `~/.cloudflared/config.yml` or `/etc/cloudflared/config.yml`).

2.  **Define Ingress Rules**
    Map your chosen hostname to `http://127.0.0.1:5050`.

    ```yaml
    tunnel: <your-tunnel-uuid>
    credentials-file: /path/to/credentials.json

    ingress:
      - hostname: gallery.yourdomain.com
        service: http://127.0.0.1:5050
      - service: http_status:404
    ```

3.  **Restart Tunnel**
    Restart the service to apply changes.

    ```bash
    sudo systemctl restart cloudflared
    ```

## Verification

1.  **Check Local Binding**
    Ensure the application is listening *only* on the localhost interface.

    ```bash
    ss -ltn | grep 5050
    ```
    **Expected Output:** `127.0.0.1:5050`

2.  **Check Public Access**
    Visit `https://gallery.yourdomain.com`. The application should load securely over HTTPS.

## Maintenance

### Database Backup
The SQLite database is stored in a named Docker volume. To create a backup:

```bash
docker cp $(docker compose ps -q web):/app/data/gallery.db ./gallery-backup.db
```

### Application Update
To update the application code and rebuild the container:

```bash
git pull
docker compose up -d --build
```

## Troubleshooting

*   **502 Bad Gateway (Cloudflare):**
    *   Ensure the Docker container is running: `docker compose ps`
    *   Verify connectivity: `curl -I http://127.0.0.1:5050`
*   **CSRF Errors:**
    *   Verify `DEBUG=0` in `.env`.
    *   Ensure you are accessing the site via HTTPS (Cloudflare handles SSL termination).
*   **Rate Limits:**
    *   If users share the Cloudflare IP, configure `RATELIMIT_STORAGE_URI` in `.env` to use Redis to properly track limits across workers.