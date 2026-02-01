"""Tests for GET / and GET /api/assets."""

import pytest


def test_index_returns_200(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"<!DOCTYPE" in r.data or b"<html" in r.data


def test_api_assets_returns_200(client):
    r = client.get("/api/assets")
    assert r.status_code == 200
    data = r.get_json()
    assert "assets" in data
    assert "has_more" in data
    assert isinstance(data["assets"], list)


def test_api_assets_pagination(client):
    r = client.get("/api/assets?page=1")
    assert r.status_code == 200
    r2 = client.get("/api/assets?page=2")
    assert r2.status_code == 200


def test_api_assets_search_param(client):
    r = client.get("/api/assets?q=test")
    assert r.status_code == 200
    data = r.get_json()
    assert "assets" in data


def test_api_assets_invalid_page(client):
    r = client.get("/api/assets?page=0")
    assert r.status_code == 200
    data = r.get_json()
    assert "assets" in data
