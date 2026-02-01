# Lumina Host

A decoupled image gallery application that leverages Headless WordPress for robust media management while delivering a lightweight, custom Flask frontend.

## Demo

[![Lumina Host Demo](https://img.youtube.com/vi/X6CKQiNb8yU/0.jpg)](https://youtu.be/X6CKQiNb8yU)

## Features

* Decoupled Architecture: Application logic (Flask) is separated from media storage (WordPress).
* Local Caching: SQLite stores metadata for instant page loads, minimizing API calls.
* Glassmorphic UI: Modern, dark-themed interface designed with Tailwind CSS.
* Mock Mode: Built-in simulation for testing without a live WordPress instance.
* Security First: Sanitized filenames and environment-variable based configuration.
* AMT (Authentication, Authorization, Multi-Tenancy): User login, role-based access, tenant isolation, and API token authentication.

## Technical Stack

* Backend: Python 3, Flask, Flask-Login
* Database: SQLite
* Frontend: Tailwind CSS, Font Awesome
* Integration: WordPress REST API

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/1999AZZAR/lumina-host.git
   cd lumina-host
   ```

2. Set up Virtual Environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install Dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Configuration:
   The project includes an `example.env` file. You must rename it to `.env` to configure your environment.

   ```bash
   cp example.env .env
   ```

   * Mock Mode: Leave `WP_*` variables empty (or delete them) to test with simulated uploads.
   * Live Mode: Fill in your WordPress credentials to enable real CDN hosting.
   
   **[Read the WordPress Setup Guide](WORDPRESS_SETUP.md)** for detailed instructions on getting your API URL and Application Password.

   ```env
   WP_API_URL=https://your-site.com/wp-json/wp/v2/media
   WP_USER=your_username
   WP_PASS=your_application_password
   FLASK_SECRET_KEY=generate-a-random-string-here
   ```

   **AMT (optional):** To enable login and per-user/tenant assets, set in `.env`. The app creates a default tenant and admin user at startup when `ADMIN_PASSWORD` is set (no migration required):

   ```env
   ENABLE_REGISTRATION=0
   API_TOKEN_EXPIRY_DAYS=90
   ADMIN_USERNAME=admin
   ADMIN_EMAIL=admin@localhost
   ADMIN_PASSWORD=secret
   ```

   Log in at `/login` with `ADMIN_USERNAME` / `ADMIN_PASSWORD`. To assign existing gallery assets to the default tenant (e.g. after upgrading), run once: `python -m migrations.add_user_system`.

5. Run the Application:

   ```bash
   python app.py
   ```

   Visit `http://127.0.0.1:5050` in your browser. Log in at `/login` to upload and delete assets. Guests can browse; upload and delete require authentication.

## Docker

Using Docker Compose (see [docker-compose.yml](docker-compose.yml)):

```bash
cp example.env .env
# Edit .env: set FLASK_SECRET_KEY, WP_* if needed, and ADMIN_USERNAME/ADMIN_EMAIL/ADMIN_PASSWORD for AMT.
docker compose up -d
```

The app creates the default admin at startup when `ADMIN_PASSWORD` is set in `.env`. Open `http://localhost:5050` and log in with `ADMIN_USERNAME` / `ADMIN_PASSWORD`. To assign existing gallery assets to the default tenant, run once: `docker compose exec web python -m migrations.add_user_system`.

## Production

For production deployments:

* **HTTPS:** Serve the app behind HTTPS. Set `SESSION_COOKIE_SECURE` via environment (session cookies are sent only over HTTPS when not in debug).
* **Rate limits:** Set `RATELIMIT_STORAGE_URL` (e.g. to your Redis URL) so Flask-Limiter uses Redis instead of in-memory storage; otherwise limits are per-process and reset on restart.
* **Admin password:** Use a strong `ADMIN_PASSWORD` (at least 8 characters, with letters and digits). `ADMIN_USERNAME` and `ADMIN_EMAIL` must be valid (alphanumeric/underscore username, valid email).

## Contributing

Please see CONTRIBUTING.md for details on our code of conduct, and the process for submitting pull requests to us.

## License

This project is licensed under the MIT License - see the LICENSE file for details.