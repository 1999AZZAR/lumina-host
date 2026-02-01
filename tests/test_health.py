"""Tests for GET /health."""

import pytest


def test_health_returns_200(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] in ("healthy", "degraded")
    assert data["db"] == "up"


def test_health_get_only(client):
    r = client.post("/health")
    assert r.status_code == 405
