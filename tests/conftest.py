"""Pytest fixtures and test env. Set env before importing app."""

import os
import tempfile

import pytest

# Set test env before any project imports.
_tmpdir = tempfile.mkdtemp(prefix="image_host_test_")
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
os.environ["TESTING"] = "1"
os.environ["ADMIN_PASSWORD"] = "admin123"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_EMAIL"] = "admin@localhost"
os.environ["ENABLE_REGISTRATION"] = "1"
# Leave WP unset so wordpress_api uses mock mode for upload/delete.
if "WP_API_URL" in os.environ:
    del os.environ["WP_API_URL"]
if "WP_USER" in os.environ:
    del os.environ["WP_USER"]
if "WP_PASS" in os.environ:
    del os.environ["WP_PASS"]

import app as app_module
import database

app_module.database.init_db()
app_module.ensure_default_admin()

app = app_module.app
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False


@pytest.fixture
def client():
    return app.test_client()


@pytest.fixture
def app_context():
    with app.app_context():
        yield


def _login(client, username: str = "admin", password: str = "admin123"):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


@pytest.fixture
def auth_client(client):
    """Client with session logged in as admin."""
    _login(client, "admin", "admin123")
    return client


@pytest.fixture
def bearer_token(client):
    """Create an API token and return (raw_token, token_id)."""
    _login(client, "admin", "admin123")
    r = client.post(
        "/api/tokens",
        json={"name": "test-token"},
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 201
    data = r.get_json()
    return data["token"], data["id"]
