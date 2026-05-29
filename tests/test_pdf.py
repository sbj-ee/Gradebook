from tests.conftest import add_assignment, add_student, make_course

# A distinctive name we can assert never appears in the generated PDFs.
SECRET_NAME = "Zelda Quackenbush"


def _setup(client, auth):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid, student_id="S777", name=SECRET_NAME)
    aid = add_assignment(client, cid, category="exam", name="Midterm", max_points=100)
    client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 88})
    return cid, sid, aid


def test_assignment_pdf_basics(client, auth):
    cid, sid, aid = _setup(client, auth)
    resp = client.get(f"/assignments/{aid}/results.pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:4] == b"%PDF"
    assert "attachment" in resp.headers["Content-Disposition"]
    assert resp.headers["Content-Disposition"].endswith('.pdf"')


def test_assignment_pdf_has_id_not_name(client, auth):
    cid, sid, aid = _setup(client, auth)
    body = client.get(f"/assignments/{aid}/results.pdf").data
    assert b"S777" in body                       # student ID present
    assert SECRET_NAME.encode() not in body      # name absent
    assert b"Zelda" not in body


def test_gradebook_pdf_basics(client, auth):
    cid, sid, aid = _setup(client, auth)
    resp = client.get(f"/courses/{cid}/gradebook.pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:4] == b"%PDF"


def test_gradebook_pdf_has_id_not_name(client, auth):
    cid, sid, aid = _setup(client, auth)
    body = client.get(f"/courses/{cid}/gradebook.pdf").data
    assert b"S777" in body
    assert b"Zelda" not in body


def test_pdf_exports_require_course_owner(client, auth):
    cid, sid, aid = _setup(client, auth)
    auth.logout()
    auth.register(username="bob")
    assert client.get(f"/assignments/{aid}/results.pdf").status_code == 403
    assert client.get(f"/courses/{cid}/gradebook.pdf").status_code == 403


def test_pdf_exports_require_login(client, auth):
    cid, sid, aid = _setup(client, auth)
    auth.logout()
    resp = client.get(f"/courses/{cid}/gradebook.pdf")
    assert resp.status_code in (302, 303)
    assert "/auth/login" in resp.headers["Location"]


def test_assignment_pdf_missing_404(client, auth):
    auth.register()
    assert client.get("/assignments/9999/results.pdf").status_code == 404


def test_gradebook_pdf_with_extra_credit_and_ungraded(client, auth):
    # Mix of an extra-credit assignment and an ungraded student exercises the
    # '-' fallbacks and the EC column header without raising.
    auth.register()
    cid = make_course(client)
    add_student(client, cid, student_id="S1", name="Alpha One")
    add_student(client, cid, student_id="S2", name="Beta Two")  # left ungraded
    ec = client.post(
        f"/api/courses/{cid}/assignments",
        json={"category": "homework", "name": "Bonus", "max_points": 5, "extra_credit": True},
    ).get_json()["id"]
    client.post(f"/api/assignments/{ec}/grades", json={"student_id": 1, "points": 3})
    resp = client.get(f"/courses/{cid}/gradebook.pdf")
    assert resp.status_code == 200
    assert resp.data[:4] == b"%PDF"
