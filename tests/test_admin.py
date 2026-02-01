"""Tests for GET/POST /admin/users and DELETE /admin/users/<id>."""

import pytest

import database


def test_admin_list_requires_auth(client):
    r = client.get("/admin/users", follow_redirects=False)
    assert r.status_code in (302, 401)


def test_admin_list_requires_admin_role(client):
    # Login as a regular user if we had one; we only have admin from ensure_default_admin.
    # So unauthenticated -> 302 to login. Authenticated as admin -> 200.
    r = client.get("/admin/users", follow_redirects=False)
    assert r.status_code in (302, 401)
    client.post("/login", data={"username": "admin", "password": "admin123"})
    r = client.get("/admin/users")
    assert r.status_code == 200
    assert b"users" in r.data or b"Users" in r.data or b"admin" in r.data


def test_admin_create_user_requires_admin(auth_client):
    r = auth_client.post(
        "/admin/users",
        json={
            "username": "staff1",
            "email": "staff1@localhost",
            "password": "pass1234",
            "role": "user",
        },
        headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 201
    data = r.get_json()
    assert "id" in data or "username" in data


def test_admin_create_user_validation(auth_client):
    r = auth_client.post(
        "/admin/users",
        json={"username": "a", "email": "invalid", "password": "short"},
        headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 400


def test_admin_delete_user_requires_admin(client):
    r = client.delete("/admin/users/999", headers={"X-Requested-With": "XMLHttpRequest"})
    assert r.status_code in (302, 401)


def test_admin_delete_own_account_forbidden(auth_client):
    # Get current user id from session by listing users and finding admin
    users = database.list_users()
    admin = next((u for u in users if u.get("username") == "admin"), None)
    assert admin is not None
    admin_id = admin["id"]
    r = auth_client.delete(
        f"/admin/users/{admin_id}",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 400
    data = r.get_json()
    assert "error" in data and ("own" in data["error"].lower() or "delete" in data["error"].lower())


def test_admin_delete_nonexistent(auth_client):
    r = auth_client.delete(
        "/admin/users/999999",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 404


def test_admin_delete_invalid_id(auth_client):
    r = auth_client.delete(
        "/admin/users/0",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 400
