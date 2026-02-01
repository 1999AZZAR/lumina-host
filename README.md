# Lumina Host

A decoupled image gallery application that leverages Headless WordPress for robust media management while delivering a lightweight, custom Flask frontend.

## Demo

[![Lumina Host Demo](https://img.youtube.com/vi/X6CKQiNb8yU/0.jpg)](https://youtu.be/X6CKQiNb8yU)

## Features

* **Decoupled Architecture:** Application logic (Flask) is separated from media storage (WordPress).
* **High Performance:**
    *   **Local Caching:** SQLite stores metadata for instant page loads.
    *   **Connection Pooling:** Reuses TCP connections to WordPress for faster bulk operations.
    *   **Background Processing:** Uploads and deletions are offloaded to background threads.
    *   **Image Optimization:** Client-side resizing (>2560px), compression, and metadata stripping (Pillow) to ensure fast, reliable uploads.
* **Resilience:** Automatic retries with exponential backoff for transient WordPress errors (500/502/503).
* **Glassmorphic UI:** Modern, dark-themed interface designed with Tailwind CSS.
* **Security First:** Sanitized filenames (standardized to `MMDDYY_HHMM_WXYZ`), secure cookies, and environment-variable based configuration.
* **AMT (Authentication, Authorization, Multi-Tenancy):** User login, role-based access, tenant isolation, and API token authentication.

## Technical Stack

* **Backend:** Python 3.12, Flask, Flask-Login, Gunicorn (Production)
* **Database:** SQLite
* **Frontend:** Tailwind CSS, Font Awesome
* **Integration:** WordPress REST API (with connection pooling & retries)

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

   * **Mock Mode:** Leave `WP_*` variables empty (or delete them) to test with simulated uploads.
   * **Live Mode:** Fill in WordPress credentials in `.env` or in the app (Profile, admin only: WordPress integration).
   * **Dev Mode:** Set `DEBUG=1` in `.env` for local development to avoid secure cookie issues over HTTP.
   
   **[Read the WordPress Setup Guide](docs/WORDPRESS_SETUP.md)** for detailed instructions on getting your API URL and Application Password.

   ```env
   WP_API_URL=https://your-site.com/wp-json/wp/v2/media
   WP_USER=your_username
   WP_PASS=your_application_password
   FLASK_SECRET_KEY=generate-a-random-string-here
   DEBUG=1
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
   # Development
   python app.py
   ```

   Visit `http://127.0.0.1:5050` in your browser. Log in at `/login` to upload and delete assets. Guests can browse; upload and delete require authentication.

## Running tests

From the project root with the virtualenv activated:

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

Tests use an isolated SQLite database and mock WordPress; no `.env` credentials are required. See [docs/API.md](docs/API.md) for endpoint coverage.

## Docker

The Docker setup uses Gunicorn for production-grade performance.

```bash
cp example.env .env
# Edit .env: FLASK_SECRET_KEY; for AMT set ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD. 
# Ensure RATELIMIT_STORAGE_URL is set to 'redis://redis:6379/1' (or similar) in .env for Docker.

docker compose up -d --build
```

The database is stored in a named volume `gallery_data` (DB_PATH=/app/data/gallery.db). The app creates the default admin at startup when `ADMIN_PASSWORD` is set in `.env`. Open `http://localhost:5050` and log in; admins can set WordPress credentials under Profile > WordPress integration. 

## Production

For production deployments (outside Docker):

* **HTTPS:** Serve the app behind HTTPS. `SESSION_COOKIE_SECURE` is automatically enabled when `DEBUG` is not set.
* **Server:** Use a WSGI server like Gunicorn (included in requirements) instead of `python app.py`.
* **Rate limits:** Set `RATELIMIT_STORAGE_URI` (e.g., `redis://localhost:6379/1`) so Flask-Limiter uses Redis.
* **Admin password:** Use a strong `ADMIN_PASSWORD`.

For full API and usage documentation, see [docs/](docs/).

## Contributing

Please see CONTRIBUTING.md for details on our code of conduct, and the process for submitting pull requests to us.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
