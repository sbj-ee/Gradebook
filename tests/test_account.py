def test_update_contact_details(client, auth, user_row):
    auth.register()
    resp = client.post(
        "/account",
        data={"action": "profile", "email": "alice@example.com", "phone": "+15551112222"},
        follow_redirects=True,
    )
    assert b"Contact details updated." in resp.data
    row = user_row("alice")
    assert row["email"] == "alice@example.com"
    assert row["phone"] == "+15551112222"


def test_change_password(client, auth):
    auth.register()
    resp = client.post(
        "/account",
        data={
            "action": "password",
            "current_password": "secret",
            "new_password": "newpass",
            "confirm_password": "newpass",
        },
        follow_redirects=True,
    )
    assert b"Password changed." in resp.data
    auth.logout()
    assert auth.login(password="newpass").status_code in (302, 303)


def test_change_password_wrong_current(client, auth):
    auth.register()
    resp = client.post(
        "/account",
        data={
            "action": "password",
            "current_password": "wrong",
            "new_password": "newpass",
            "confirm_password": "newpass",
        },
        follow_redirects=True,
    )
    assert b"Current password is incorrect." in resp.data


def test_duplicate_email_rejected(client, auth):
    auth.register(username="alice", email="dup@example.com")
    auth.logout()
    auth.register(username="bob")
    resp = client.post(
        "/account",
        data={"action": "profile", "email": "dup@example.com", "phone": ""},
        follow_redirects=True,
    )
    assert b"already in use" in resp.data
