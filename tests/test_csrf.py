import os
import re
import tempfile

import pytest

from app import create_app


@pytest.fixture
def csrf_client():
    db_fd, db_path = tempfile.mkstemp(suffix=".sqlite")
    app = create_app(
        {"TESTING": True, "DATABASE": db_path, "SECRET_KEY": "test",
         "CSRF_ENABLED": True}
    )
    yield app.test_client()
    os.close(db_fd)
    os.unlink(db_path)


def _token(html):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None


def test_form_page_renders_a_token(csrf_client):
    assert 'name="csrf_token"' in csrf_client.get("/auth/login").get_data(as_text=True)


def test_post_without_token_is_rejected(csrf_client):
    resp = csrf_client.post("/auth/register", data={"username": "a", "password": "b"})
    assert resp.status_code == 400


def test_post_with_bad_token_is_rejected(csrf_client):
    csrf_client.get("/auth/register")  # establishes a session token
    resp = csrf_client.post(
        "/auth/register", data={"username": "a", "password": "b", "csrf_token": "nope"}
    )
    assert resp.status_code == 400


def test_post_with_valid_token_succeeds(csrf_client):
    token = _token(csrf_client.get("/auth/register").get_data(as_text=True))
    assert token
    resp = csrf_client.post(
        "/auth/register",
        data={"username": "a", "password": "b", "csrf_token": token},
    )
    assert resp.status_code in (302, 303)  # registered and redirected


def test_api_is_exempt_from_csrf(csrf_client):
    # Register through the web form (with a token) to get a session cookie...
    token = _token(csrf_client.get("/auth/register").get_data(as_text=True))
    csrf_client.post(
        "/auth/register",
        data={"username": "a", "password": "b", "csrf_token": token},
    )
    # ...then a JSON API POST without any CSRF token still works.
    resp = csrf_client.post("/api/courses", json={"name": "Chem"})
    assert resp.status_code == 201
