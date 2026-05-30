from tests.conftest import add_assignment, add_student, make_course

SECRET_NAME = "Wilhelmina Featherstonehaugh"


def _setup(client, auth):
    auth.register()
    cid = make_course(client, weights={"homework": 100, "quiz": 0, "exam": 0})
    sid = add_student(client, cid, student_id="S55", name=SECRET_NAME)
    aid = add_assignment(client, cid, category="homework", name="HW1", max_points=10)
    client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 9})
    return cid, sid


def test_report_card_page(client, auth):
    cid, sid = _setup(client, auth)
    resp = client.get(f"/courses/{cid}/students/{sid}/report")
    assert resp.status_code == 200
    assert b"Report card" in resp.data
    assert b"S55" in resp.data
    assert b"HW1" in resp.data
    assert b"90" in resp.data  # category/final percent


def test_report_card_pdf_id_not_name(client, auth):
    cid, sid = _setup(client, auth)
    resp = client.get(f"/courses/{cid}/students/{sid}/report.pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:4] == b"%PDF"
    assert b"S55" in resp.data
    assert SECRET_NAME.encode() not in resp.data
    assert b"Wilhelmina" not in resp.data


def test_report_card_requires_owner(client, auth):
    cid, sid = _setup(client, auth)
    auth.logout()
    auth.register(username="bob")
    assert client.get(f"/courses/{cid}/students/{sid}/report").status_code == 403
    assert client.get(f"/courses/{cid}/students/{sid}/report.pdf").status_code == 403


def test_report_card_404_when_not_enrolled(client, auth):
    auth.register()
    c1 = make_course(client)
    c2 = make_course(client)
    sid = add_student(client, c1, student_id="S1", name="Pat")
    assert client.get(f"/courses/{c2}/students/{sid}/report").status_code == 404


def test_report_card_marks_dropped(client, auth):
    auth.register()
    cid = client.post(
        "/api/courses",
        json={"name": "C", "weights": {"homework": 100, "quiz": 0, "exam": 0},
              "drop_lowest": {"homework": 1, "quiz": 0, "exam": 0}},
    ).get_json()["id"]
    sid = add_student(client, cid, student_id="S1", name="Pat")
    a1 = add_assignment(client, cid, category="homework", name="Low", max_points=10)
    a2 = add_assignment(client, cid, category="homework", name="High", max_points=10)
    client.post(f"/api/assignments/{a1}/grades", json={"student_id": sid, "points": 2})
    client.post(f"/api/assignments/{a2}/grades", json={"student_id": sid, "points": 10})
    page = client.get(f"/courses/{cid}/students/{sid}/report").data
    assert b"dropped" in page
