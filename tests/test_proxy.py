"""Tests for GET /proxy_download."""

import pytest


def test_proxy_missing_url_returns_400(client):
    r = client.get("/proxy_download")
    assert r.status_code == 400
    data = r.get_json()
    assert "error" in data and ("url" in data["error"].lower() or "missing" in data["error"].lower())


def test_proxy_disallowed_url_returns_403(client):
    r = client.get("/proxy_download?url=https://evil.com/image.jpg")
    assert r.status_code == 403
    data = r.get_json()
    assert "error" in data
