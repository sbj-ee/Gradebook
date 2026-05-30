from tests.conftest import make_course


def test_non_admin_cannot_reach_admin(client, auth):
    auth.register()
    assert client.get("/admin/", follow_redirects=False).status_code == 403


def test_logged_out_redirected_to_login(client):
    resp = client.get("/admin/")
    assert resp.status_code in (302, 303)
    assert "/auth/login" in resp.headers["Location"]


def test_admin_dashboard(client, auth, make_admin):
    auth.register(username="root")
    make_admin("root")
    resp = client.get("/admin/")
    assert resp.status_code == 200
    assert b"control panel" in resp.data


def test_admin_can_delete_course(client, auth, make_admin):
    auth.register(username="root")
    make_admin("root")
    cid = make_course(client)
    resp = client.post(f"/admin/courses/{cid}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert client.get(f"/api/courses/{cid}").status_code == 404


def test_admin_cannot_delete_self(client, auth, make_admin, user_row):
    auth.register(username="root")
    make_admin("root")
    uid = user_row("root")["id"]
    resp = client.post(f"/admin/users/{uid}/delete", follow_redirects=True)
    assert b"cannot delete your own account" in resp.data


def test_grades_csv_returns_401_when_logged_out(client):
    # Download endpoint fails loudly rather than redirecting to an HTML login page.
    assert client.get("/admin/reports/grades.csv").status_code == 401


def test_grades_csv_export(client, auth, make_admin):
    auth.register(username="root")
    make_admin("root")
    cid = make_course(client)
    sid = client.post(
        f"/api/courses/{cid}/students", json={"student_id": "S7", "name": "Sam"}
    ).get_json()["id"]
    aid = client.post(
        f"/api/courses/{cid}/assignments",
        json={"category": "exam", "name": "Final", "max_points": 100},
    ).get_json()["id"]
    client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 91})
    resp = client.get("/admin/reports/grades.csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert b"S7" in resp.data
    assert b"Sam" in resp.data
    assert b"91" in resp.data
