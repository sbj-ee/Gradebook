import io

from tests.conftest import add_assignment, add_student, make_course


def _csv(client, url, text, field="file", filename="data.csv"):
    return client.post(
        url,
        data={field: (io.BytesIO(text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_import_roster(client, auth):
    auth.register()
    cid = make_course(client)
    csv = "student_id,name,email\nS1,Ann,ann@x.com\nS2,Bob,\nS3,Cy,\n"
    resp = _csv(client, f"/courses/{cid}/import-roster", csv)
    assert resp.status_code == 200
    roster = client.get(f"/api/courses/{cid}/students").get_json()
    assert {s["student_id"] for s in roster} == {"S1", "S2", "S3"}
    assert next(s for s in roster if s["student_id"] == "S1")["email"] == "ann@x.com"


def test_import_roster_tolerates_bom_and_header_case(client, auth):
    auth.register()
    cid = make_course(client)
    csv = "﻿Student ID,Name\nS9,Zoe\n"  # BOM + spaced/cased headers
    _csv(client, f"/courses/{cid}/import-roster", csv)
    roster = client.get(f"/api/courses/{cid}/students").get_json()
    assert roster[0]["student_id"] == "S9"
    assert roster[0]["name"] == "Zoe"


def test_import_roster_skips_already_enrolled(client, auth):
    auth.register()
    cid = make_course(client)
    add_student(client, cid, student_id="S1", name="Ann")
    resp = _csv(client, f"/courses/{cid}/import-roster", "student_id,name\nS1,Ann\nS2,Bob\n")
    assert b"1 added, 1 already enrolled" in resp.data


def test_import_grades(client, auth):
    auth.register()
    cid = make_course(client, weights={"homework": 100, "quiz": 0, "exam": 0})
    s1 = add_student(client, cid, student_id="S1", name="Ann")
    s2 = add_student(client, cid, student_id="S2", name="Bob")
    aid = add_assignment(client, cid, category="homework", name="HW1", max_points=10)
    _csv(client, f"/assignments/{aid}/import-grades", "student_id,points\nS1,9\nS2,7\n")
    assert client.get(f"/api/courses/{cid}/students/{s1}/grade").get_json()["categories"]["homework"]["percentage"] == 90.0
    assert client.get(f"/api/courses/{cid}/students/{s2}/grade").get_json()["categories"]["homework"]["percentage"] == 70.0


def test_import_grades_blank_clears(client, auth):
    auth.register()
    cid = make_course(client, weights={"homework": 100, "quiz": 0, "exam": 0})
    sid = add_student(client, cid, student_id="S1", name="Ann")
    aid = add_assignment(client, cid, category="homework", name="HW1", max_points=10)
    client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 8})
    resp = _csv(client, f"/assignments/{aid}/import-grades", "student_id,points\nS1,\n")
    assert b"1 cleared" in resp.data
    assert client.get(f"/api/courses/{cid}/students/{sid}/grade").get_json()["categories"]["homework"]["percentage"] is None


def test_import_grades_reports_bad_rows(client, auth):
    auth.register()
    cid = make_course(client)
    add_student(client, cid, student_id="S1", name="Ann")
    aid = add_assignment(client, cid, category="homework", name="HW1", max_points=10)
    # S9 not enrolled; S1 over max.
    resp = _csv(client, f"/assignments/{aid}/import-grades",
                "student_id,points\nS9,5\nS1,99\n")
    assert b"not enrolled" in resp.data
    assert b"exceed" in resp.data


def test_import_requires_owner(client, auth):
    auth.register()
    cid = make_course(client)
    auth.logout()
    auth.register(username="bob")
    resp = client.post(
        f"/courses/{cid}/import-roster",
        data={"file": (io.BytesIO(b"student_id,name\nS1,Ann\n"), "r.csv")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403
