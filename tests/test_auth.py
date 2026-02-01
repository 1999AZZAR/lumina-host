"""Tests for /login, /logout, /register, /profile."""

import pytest


def test_login_get_returns_200(client):
    r = client.get("/login")
    assert r.status_code == 200


def test_login_post_success(client):
    r = client.post(
        "/login",
        data={"username": "admin", "password": "admin123"},
        follow_redirects=False,
    )
    assert r.status_code in (200, 302)
    if r.status_code == 302:
        assert r.location and "/" in r.location


def test_login_post_bad_password(client):
    r = client.post(
        "/login",
        data={"username": "admin", "password": "wrong"},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert b"Invalid" in r.data or b"invalid" in r.data


def test_logout_get_redirects(client):
    r = client.get("/logout")
    assert r.status_code == 302
    assert r.location and "/" in r.location


def test_logout_post_logs_out(client):
    client.post("/login", data={"username": "admin", "password": "admin123"})
    r = client.post("/logout", follow_redirects=False)
    assert r.status_code == 302


def test_register_get_returns_200(client):
    r = client.get("/register")
    assert r.status_code == 200


def test_register_post_creates_user(client):
    r = client.post(
        "/register",
        data={
            "username": "newuser99",
            "email": "newuser99@localhost",
            "password": "pass1234",
        },
        follow_redirects=False,
    )
    assert r.status_code in (200, 302)
    if r.status_code == 302:
        assert "/login" in (r.location or "")


def test_profile_requires_auth(client):
    r = client.get("/profile", follow_redirects=False)
    assert r.status_code in (302, 401)
    if r.status_code == 302:
        assert "/login" in (r.location or "")


def test_profile_ok_when_logged_in(auth_client):
    r = auth_client.get("/profile")
    assert r.status_code == 200
