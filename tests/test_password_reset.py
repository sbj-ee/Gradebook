import hashlib

from app.db import get_db


def _token_for(app, username):
    """Return a usable reset token for ``username`` by reading the hash row and
    brute-forcing nothing — instead we re-issue via the forgot flow and capture it
    from the database is impossible (only the hash is stored), so we generate a
    known token, store its hash directly, and return the token."""
    token = "known-test-token"
    with app.app_context():
        db = get_db()
        user = db.execute(
            "SELECT id FROM user WHERE username = ?", (username,)
        ).fetchone()
        db.execute("DELETE FROM password_reset WHERE user_id = ?", (user["id"],))
        db.execute(
            "INSERT INTO password_reset (user_id, token_hash, expires_at) "
            "VALUES (?, ?, datetime('now', '+1 hour'))",
            (user["id"], hashlib.sha256(token.encode()).hexdigest()),
        )
        db.commit()
    return token


def test_forgot_password_shows_neutral_message(client, auth):
    auth.register(email="alice@example.com")
    auth.logout()
    resp = client.post(
        "/auth/forgot", data={"identifier": "alice@example.com"}, follow_redirects=True
    )
    assert b"a password reset link has been sent" in resp.data


def test_forgot_unknown_account_same_message(client):
    resp = client.post(
        "/auth/forgot", data={"identifier": "nobody"}, follow_redirects=True
    )
    assert b"a password reset link has been sent" in resp.data


def test_reset_password_with_valid_token(client, auth, app):
    auth.register(email="alice@example.com")
    auth.logout()
    token = _token_for(app, "alice")
    resp = client.post(
        f"/auth/reset/{token}",
        data={"new_password": "brandnew", "confirm_password": "brandnew"},
        follow_redirects=True,
    )
    assert b"Your password has been reset." in resp.data
    assert auth.login(password="brandnew").status_code in (302, 303)


def test_reset_token_is_single_use(client, auth, app):
    auth.register(email="alice@example.com")
    auth.logout()
    token = _token_for(app, "alice")
    client.post(
        f"/auth/reset/{token}",
        data={"new_password": "brandnew", "confirm_password": "brandnew"},
        follow_redirects=True,
    )
    # Reusing the token now fails.
    resp = client.post(
        f"/auth/reset/{token}",
        data={"new_password": "again", "confirm_password": "again"},
        follow_redirects=True,
    )
    assert b"invalid or has expired" in resp.data


def test_invalid_token_rejected(client):
    resp = client.get("/auth/reset/not-a-real-token", follow_redirects=True)
    assert b"invalid or has expired" in resp.data
