import base64
import os
import tempfile

import pytest

from app import create_app
from app.db import get_db


@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp(suffix=".sqlite")
    app = create_app(
        {"TESTING": True, "DATABASE": db_path, "SECRET_KEY": "test",
         "CSRF_ENABLED": False}
    )
    yield app
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


class AuthActions:
    def __init__(self, client):
        self._client = client

    def register(self, username="alice", password="secret", email=None, phone=None):
        data = {"username": username, "password": password}
        if email is not None:
            data["email"] = email
        if phone is not None:
            data["phone"] = phone
        return self._client.post("/auth/register", data=data)

    def login(self, username="alice", password="secret", follow_redirects=False):
        return self._client.post(
            "/auth/login",
            data={"username": username, "password": password},
            follow_redirects=follow_redirects,
        )

    def logout(self):
        return self._client.get("/auth/logout")


@pytest.fixture
def auth(client):
    return AuthActions(client)


@pytest.fixture
def make_admin(app):
    def _make_admin(username):
        with app.app_context():
            db = get_db()
            db.execute("UPDATE user SET is_admin = 1 WHERE username = ?", (username,))
            db.commit()

    return _make_admin


@pytest.fixture
def is_admin(app):
    def _is_admin(username):
        with app.app_context():
            row = get_db().execute(
                "SELECT is_admin FROM user WHERE username = ?", (username,)
            ).fetchone()
            return bool(row and row["is_admin"])

    return _is_admin


@pytest.fixture
def user_row(app):
    def _user_row(username):
        with app.app_context():
            r = get_db().execute(
                "SELECT * FROM user WHERE username = ?", (username,)
            ).fetchone()
            return dict(r) if r else None

    return _user_row


@pytest.fixture
def notifications(app):
    def _notifications():
        with app.app_context():
            return [
                dict(r)
                for r in get_db()
                .execute("SELECT * FROM notification ORDER BY id")
                .fetchall()
            ]

    return _notifications


def basic_auth_header(username="alice", password="secret"):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def make_course(client, name="Math 101", weights=None):
    """Create a course via the API and return its id (caller must be logged in)."""
    payload = {"name": name}
    if weights is not None:
        payload["weights"] = weights
    return client.post("/api/courses", json=payload).get_json()["id"]


def add_student(client, course_id, student_id="S1", name="Pat", email=None, phone=None):
    data = {"student_id": student_id, "name": name}
    if email is not None:
        data["email"] = email
    if phone is not None:
        data["phone"] = phone
    return client.post(f"/api/courses/{course_id}/students", json=data).get_json()["id"]


def add_assignment(client, course_id, category="homework", name="HW1", max_points=100):
    return client.post(
        f"/api/courses/{course_id}/assignments",
        json={"category": category, "name": name, "max_points": max_points},
    ).get_json()["id"]
