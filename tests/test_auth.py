def test_register_logs_in_and_redirects(client, auth):
    resp = auth.register()
    assert resp.status_code in (302, 303)
    # Now authenticated: the new-course page is reachable.
    assert client.get("/courses/new").status_code == 200


def test_register_requires_username_and_password(client):
    resp = client.post("/auth/register", data={"username": "", "password": ""},
                       follow_redirects=True)
    assert b"Username is required." in resp.data


def test_duplicate_username_rejected(client, auth):
    auth.register()
    auth.logout()
    resp = client.post(
        "/auth/register", data={"username": "alice", "password": "x"},
        follow_redirects=True,
    )
    assert b"already taken" in resp.data


def test_login_logout(client, auth):
    auth.register()
    auth.logout()
    resp = auth.login(follow_redirects=True)
    assert resp.status_code == 200
    auth.logout()
    # Protected page redirects to login when logged out.
    resp = client.get("/courses/new")
    assert resp.status_code in (302, 303)
    assert "/auth/login" in resp.headers["Location"]


def test_login_wrong_password(client, auth):
    auth.register()
    auth.logout()
    resp = client.post(
        "/auth/login", data={"username": "alice", "password": "nope"},
        follow_redirects=True,
    )
    assert b"Incorrect username or password." in resp.data
