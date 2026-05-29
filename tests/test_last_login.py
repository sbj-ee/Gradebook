def test_first_login_has_no_previous_notice(client, auth):
    auth.register()
    auth.logout()
    resp = auth.login(follow_redirects=True)
    # The first time logging back in there's a prior login stamped at registration?
    # Registration does not stamp last_login, so the first explicit login shows no banner.
    assert b"Welcome back" not in resp.data


def test_second_login_shows_welcome_back(client, auth):
    auth.register()
    auth.logout()
    auth.login()       # first login: records last_login_at
    auth.logout()
    resp = auth.login(follow_redirects=True)  # second login: prior time available
    assert b"Welcome back" in resp.data


def test_last_login_recorded(client, auth, user_row):
    auth.register()
    auth.logout()
    assert user_row("alice")["last_login_at"] is None
    auth.login()
    assert user_row("alice")["last_login_at"] is not None
