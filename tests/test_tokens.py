"""Tests for GET/POST /api/tokens and DELETE /api/tokens/<id>."""

import pytest


def test_list_tokens_requires_auth(client):
    r = client.get("/api/tokens", headers={"X-Requested-With": "XMLHttpRequest"})
    assert r.status_code == 401


def test_list_tokens_ok(auth_client):
    r = auth_client.get("/api/tokens")
    assert r.status_code == 200
    data = r.get_json()
    assert "tokens" in data


def test_create_token_requires_auth(client):
    r = client.post(
        "/api/tokens",
        json={"name": "x"},
        headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 401


def test_create_token_returns_201(auth_client):
    r = auth_client.post(
        "/api/tokens",
        json={"name": "my-token"},
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 201
    data = r.get_json()
    assert "token" in data
    assert data.get("id")
    assert "Store this token" in (data.get("message") or "")


def test_create_token_optional_name(auth_client):
    r = auth_client.post("/api/tokens", json={}, headers={"Content-Type": "application/json"})
    assert r.status_code == 201


def test_revoke_token_requires_auth(client):
    r = client.delete(
        "/api/tokens/1",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 401


def test_revoke_token_ok(auth_client, bearer_token):
    _, token_id = bearer_token
    r = auth_client.delete(f"/api/tokens/{token_id}")
    assert r.status_code == 200
    data = r.get_json()
    assert "message" in data or "revoked" in data.lower() or "Token" in str(data)


def test_revoke_token_invalid_id(auth_client):
    r = auth_client.delete("/api/tokens/0", headers={"X-Requested-With": "XMLHttpRequest"})
    assert r.status_code == 400


def test_bearer_auth_works(client, bearer_token):
    raw_token, _ = bearer_token
    r = client.get(
        "/api/tokens",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "tokens" in data
