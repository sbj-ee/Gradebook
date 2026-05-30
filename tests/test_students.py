from tests.conftest import add_assignment, add_student, make_course


def test_edit_student_api(client, auth):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid, student_id="S1", name="Pat")
    resp = client.put(
        f"/api/students/{sid}",
        json={"student_id": "S1-new", "name": "Patricia", "email": "p@x.com"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["student_id"] == "S1-new"
    assert body["name"] == "Patricia"
    assert body["email"] == "p@x.com"
    assert "course_id" not in body  # students are global now


def test_edit_student_partial(client, auth):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid, student_id="S1", name="Pat")
    body = client.put(f"/api/students/{sid}", json={"name": "Pat Jr"}).get_json()
    assert body["name"] == "Pat Jr"
    assert body["student_id"] == "S1"  # unchanged


def test_edit_student_requires_owner(client, auth):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid, student_id="S1", name="Pat")
    auth.logout()
    auth.register(username="bob")
    assert client.put(f"/api/students/{sid}", json={"name": "Hijack"}).status_code == 403


def test_duplicate_global_student_id_rejected(client, auth):
    auth.register()
    cid = make_course(client)
    s1 = add_student(client, cid, student_id="S1", name="Pat")
    add_student(client, cid, student_id="S2", name="Sam")
    # Renaming S1's code to S2 collides with the other student.
    resp = client.put(f"/api/students/{s1}", json={"student_id": "S2"})
    assert resp.status_code == 400
    assert b"already in use" in resp.data


def test_ui_edit_student(client, auth):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid, student_id="S1", name="Pat")
    page = client.get(f"/courses/{cid}/students/{sid}/edit")
    assert page.status_code == 200
    assert b"S1" in page.data
    resp = client.post(
        f"/courses/{cid}/students/{sid}/edit",
        data={"student_id": "S9", "name": "Renamed", "email": "", "phone": ""},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    roster = client.get(f"/api/courses/{cid}/students").get_json()
    assert roster[0]["student_id"] == "S9"
    assert roster[0]["name"] == "Renamed"


def test_student_enrolled_in_multiple_courses(client, auth):
    auth.register()
    c1 = make_course(client, name="Course One")
    c2 = make_course(client, name="Course Two")
    sid1 = add_student(client, c1, student_id="S1", name="Pat")
    sid2 = add_student(client, c2, student_id="S1", name="Pat")  # same person
    assert sid1 == sid2  # one global student, two enrollments
    assert {s["student_id"] for s in client.get(f"/api/courses/{c1}/students").get_json()} == {"S1"}
    assert {s["student_id"] for s in client.get(f"/api/courses/{c2}/students").get_json()} == {"S1"}


def test_grades_are_per_course(client, auth):
    auth.register()
    c1 = make_course(client, name="Course One", weights={"homework": 100, "quiz": 0, "exam": 0})
    c2 = make_course(client, name="Course Two", weights={"homework": 100, "quiz": 0, "exam": 0})
    sid = add_student(client, c1, student_id="S1", name="Pat")
    add_student(client, c2, student_id="S1", name="Pat")
    a1 = add_assignment(client, c1, category="homework", max_points=100)
    client.post(f"/api/assignments/{a1}/grades", json={"student_id": sid, "points": 90})
    # Course 1 reflects the grade; course 2 has none for this student.
    g1 = client.get(f"/api/courses/{c1}/students/{sid}/grade").get_json()
    g2 = client.get(f"/api/courses/{c2}/students/{sid}/grade").get_json()
    assert g1["final_percentage"] == 90.0
    assert g2["final_percentage"] is None


def test_remove_unenrolls_but_keeps_student_elsewhere(client, auth):
    auth.register()
    c1 = make_course(client, name="Course One")
    c2 = make_course(client, name="Course Two")
    sid = add_student(client, c1, student_id="S1", name="Pat")
    add_student(client, c2, student_id="S1", name="Pat")
    a1 = add_assignment(client, c1, category="homework", max_points=100)
    client.post(f"/api/assignments/{a1}/grades", json={"student_id": sid, "points": 70})
    # Remove from course 1.
    client.post(f"/courses/{c1}/students/{sid}/remove", follow_redirects=True)
    assert client.get(f"/api/courses/{c1}/students").get_json() == []
    # Still enrolled in course 2.
    assert len(client.get(f"/api/courses/{c2}/students").get_json()) == 1
    # Their course-1 grade is gone.
    assert client.get(f"/api/courses/{c1}/students/{sid}/grade").status_code == 404


def test_student_grade_requires_enrollment(client, auth):
    auth.register()
    c1 = make_course(client)
    c2 = make_course(client)
    sid = add_student(client, c1, student_id="S1", name="Pat")
    # Not enrolled in c2 -> 404.
    assert client.get(f"/api/courses/{c2}/students/{sid}/grade").status_code == 404
