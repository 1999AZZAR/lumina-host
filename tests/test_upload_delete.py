"""Tests for POST /upload and POST /delete."""

import io
import pytest


def test_upload_requires_auth(client):
    r = client.post(
        "/upload",
        data={},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code in (302, 401)


def test_upload_no_file_returns_400(auth_client):
    r = auth_client.post(
        "/upload",
        data={},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 400
    data = r.get_json()
    assert "error" in data


def test_upload_valid_file(auth_client):
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    r = auth_client.post(
        "/upload",
        data={"file": (io.BytesIO(data), "test.png", "image/png")},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code in (200, 502)
    if r.status_code == 200:
        j = r.get_json()
        assert "message" in j or "assets" in j


def test_delete_requires_auth(client):
    r = client.post(
        "/delete",
        json={"ids": [1]},
        headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code in (302, 401)


def test_delete_no_ids_returns_400(auth_client):
    r = auth_client.post(
        "/delete",
        json={},
        headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 400


def test_delete_empty_ids_returns_400(auth_client):
    r = auth_client.post(
        "/delete",
        json={"ids": []},
        headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 400


def test_delete_valid_ids(auth_client):
    # Delete non-existent IDs: still 200 with message (0 deleted)
    r = auth_client.post(
        "/delete",
        json={"ids": [999998, 999999]},
        headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "message" in data
    assert "deleted_ids" in data
