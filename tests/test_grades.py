from tests.conftest import add_assignment, add_student, make_course


def test_duplicate_student_id_rejected(client, auth):
    auth.register()
    cid = make_course(client)
    assert client.post(
        f"/api/courses/{cid}/students", json={"student_id": "S1", "name": "A"}
    ).status_code == 201
    resp = client.post(
        f"/api/courses/{cid}/students", json={"student_id": "S1", "name": "B"}
    )
    assert resp.status_code == 400
    assert b"already enrolled" in resp.data


def test_invalid_category_rejected(client, auth):
    auth.register()
    cid = make_course(client)
    resp = client.post(
        f"/api/courses/{cid}/assignments",
        json={"category": "project", "name": "X", "max_points": 10},
    )
    assert resp.status_code == 400


def test_set_grade_success(client, auth):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid)
    aid = add_assignment(client, cid, max_points=20)
    resp = client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 18})
    assert resp.status_code == 201
    assert resp.get_json()["points"] == 18


def test_update_grade_returns_200(client, auth):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid)
    aid = add_assignment(client, cid, max_points=20)
    client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 10})
    resp = client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 15})
    assert resp.status_code == 200
    assert resp.get_json()["points"] == 15


def test_grade_exceeding_max_rejected(client, auth):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid)
    aid = add_assignment(client, cid, max_points=20)
    resp = client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 25})
    assert resp.status_code == 400
    assert b"exceed" in resp.data


def test_negative_grade_rejected(client, auth):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid)
    aid = add_assignment(client, cid, max_points=20)
    resp = client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": -1})
    assert resp.status_code == 400


def test_only_owner_can_grade(client, auth):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid)
    aid = add_assignment(client, cid)
    auth.logout()
    auth.register(username="bob")
    resp = client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 5})
    assert resp.status_code == 403


def test_admin_can_grade_any_course(client, auth, make_admin):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid)
    aid = add_assignment(client, cid)
    auth.logout()
    auth.register(username="root")
    make_admin("root")
    resp = client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 7})
    assert resp.status_code == 201


def test_weighted_gradebook_computation(client, auth):
    auth.register()
    cid = make_course(client, weights={"homework": 40, "quiz": 20, "exam": 40})
    sid = add_student(client, cid)
    hw = add_assignment(client, cid, category="homework", name="HW1", max_points=100)
    qz = add_assignment(client, cid, category="quiz", name="Q1", max_points=100)
    ex = add_assignment(client, cid, category="exam", name="Final", max_points=100)
    client.post(f"/api/assignments/{hw}/grades", json={"student_id": sid, "points": 90})
    client.post(f"/api/assignments/{qz}/grades", json={"student_id": sid, "points": 80})
    client.post(f"/api/assignments/{ex}/grades", json={"student_id": sid, "points": 70})
    book = client.get(f"/api/courses/{cid}/gradebook").get_json()
    row = book["students"][0]
    # (90*40 + 80*20 + 70*40) / 100 = 80
    assert row["final_percentage"] == 80.0
    assert row["letter"] == "B"


def test_ungraded_category_is_renormalized(client, auth):
    auth.register()
    cid = make_course(client, weights={"homework": 40, "quiz": 20, "exam": 40})
    sid = add_student(client, cid)
    hw = add_assignment(client, cid, category="homework", name="HW1", max_points=100)
    add_assignment(client, cid, category="exam", name="Final", max_points=100)
    # Only homework graded; quiz/exam empty -> final equals the homework percentage.
    client.post(f"/api/assignments/{hw}/grades", json={"student_id": sid, "points": 95})
    summary = client.get(f"/api/courses/{cid}/students/{sid}/grade").get_json()
    assert summary["final_percentage"] == 95.0
    assert summary["letter"] == "A"
    assert summary["categories"]["exam"]["percentage"] is None


def test_category_aggregates_multiple_assignments(client, auth):
    auth.register()
    cid = make_course(client, weights={"homework": 100, "quiz": 0, "exam": 0})
    sid = add_student(client, cid)
    hw1 = add_assignment(client, cid, category="homework", name="HW1", max_points=10)
    hw2 = add_assignment(client, cid, category="homework", name="HW2", max_points=30)
    client.post(f"/api/assignments/{hw1}/grades", json={"student_id": sid, "points": 8})
    client.post(f"/api/assignments/{hw2}/grades", json={"student_id": sid, "points": 24})
    # (8 + 24) / (10 + 30) = 80%
    summary = client.get(f"/api/courses/{cid}/students/{sid}/grade").get_json()
    assert summary["categories"]["homework"]["percentage"] == 80.0
    assert summary["final_percentage"] == 80.0


def test_api_edit_assignment(client, auth):
    auth.register()
    cid = make_course(client)
    aid = add_assignment(client, cid, category="homework", name="HW1", max_points=20)
    resp = client.put(
        f"/api/assignments/{aid}",
        json={"category": "quiz", "name": "Pop Quiz", "max_points": 15},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["category"] == "quiz"
    assert body["name"] == "Pop Quiz"
    assert body["max_points"] == 15


def test_api_edit_assignment_partial(client, auth):
    auth.register()
    cid = make_course(client)
    aid = add_assignment(client, cid, category="exam", name="Midterm", max_points=100)
    # Only renaming; category and max_points are preserved.
    body = client.put(f"/api/assignments/{aid}", json={"name": "Midterm Exam"}).get_json()
    assert body["name"] == "Midterm Exam"
    assert body["category"] == "exam"
    assert body["max_points"] == 100


def test_only_owner_can_edit_assignment(client, auth):
    auth.register()
    cid = make_course(client)
    aid = add_assignment(client, cid)
    auth.logout()
    auth.register(username="bob")
    resp = client.put(f"/api/assignments/{aid}", json={"name": "Hijacked"})
    assert resp.status_code == 403


def test_cannot_lower_max_below_existing_grade(client, auth):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid)
    aid = add_assignment(client, cid, max_points=100)
    client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 80})
    resp = client.put(f"/api/assignments/{aid}", json={"max_points": 50})
    assert resp.status_code == 400
    assert b"existing grade" in resp.data


def test_ui_edit_assignment(client, auth):
    auth.register()
    cid = make_course(client)
    aid = add_assignment(client, cid, category="homework", name="HW1", max_points=20)
    # The edit form renders with the current values.
    page = client.get(f"/assignments/{aid}/edit")
    assert page.status_code == 200
    assert b"HW1" in page.data
    resp = client.post(
        f"/assignments/{aid}/edit",
        data={"category": "exam", "name": "Final", "max_points": "200"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    updated = client.get(f"/api/courses/{cid}/assignments").get_json()[0]
    assert updated["category"] == "exam"
    assert updated["name"] == "Final"
    assert updated["max_points"] == 200


def test_extra_credit_boosts_its_category(client, auth):
    auth.register()
    cid = make_course(client, weights={"homework": 100, "quiz": 0, "exam": 0})
    sid = add_student(client, cid)
    hw = add_assignment(client, cid, category="homework", name="HW1", max_points=20)
    # Extra-credit homework assignment worth up to 5 bonus points.
    ec = client.post(
        f"/api/courses/{cid}/assignments",
        json={"category": "homework", "name": "Bonus", "max_points": 5, "extra_credit": True},
    ).get_json()
    assert ec["extra_credit"] is True
    client.post(f"/api/assignments/{hw}/grades", json={"student_id": sid, "points": 18})  # 18/20
    client.post(f"/api/assignments/{ec['id']}/grades", json={"student_id": sid, "points": 2})
    # earned 20 / possible 20 (EC doesn't add to possible) -> 100%
    summary = client.get(f"/api/courses/{cid}/students/{sid}/grade").get_json()
    assert summary["categories"]["homework"]["possible"] == 20
    assert summary["categories"]["homework"]["earned"] == 20
    assert summary["categories"]["homework"]["percentage"] == 100.0


def test_extra_credit_can_exceed_100(client, auth):
    auth.register()
    cid = make_course(client, weights={"homework": 100, "quiz": 0, "exam": 0})
    sid = add_student(client, cid)
    hw = add_assignment(client, cid, category="homework", name="HW1", max_points=20)
    ec = client.post(
        f"/api/courses/{cid}/assignments",
        json={"category": "homework", "name": "Bonus", "max_points": 5, "extra_credit": True},
    ).get_json()["id"]
    client.post(f"/api/assignments/{hw}/grades", json={"student_id": sid, "points": 20})   # full
    client.post(f"/api/assignments/{ec}/grades", json={"student_id": sid, "points": 4})     # +4 bonus
    # 24 / 20 -> 120%
    summary = client.get(f"/api/courses/{cid}/students/{sid}/grade").get_json()
    assert summary["categories"]["homework"]["percentage"] == 120.0


def test_extra_credit_defaults_off(client, auth):
    auth.register()
    cid = make_course(client)
    aid = add_assignment(client, cid)  # no extra_credit key
    a = client.get(f"/api/courses/{cid}/assignments").get_json()[0]
    assert a["extra_credit"] is False


def test_ui_add_extra_credit_assignment(client, auth):
    auth.register()
    cid = make_course(client)
    client.post(
        f"/courses/{cid}/assignments",
        data={"category": "exam", "name": "Bonus essay", "max_points": "10", "extra_credit": "1"},
        follow_redirects=True,
    )
    a = client.get(f"/api/courses/{cid}/assignments").get_json()[0]
    assert a["name"] == "Bonus essay"
    assert a["extra_credit"] is True


def test_ui_grade_entry_and_clear(client, auth):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid)
    aid = add_assignment(client, cid, max_points=100)
    # Enter a grade through the bulk web form.
    client.post(f"/assignments/{aid}/grades", data={f"points_{sid}": "88"}, follow_redirects=True)
    assert client.get(f"/api/courses/{cid}/students/{sid}/grade").get_json()["categories"]["homework"]["percentage"] == 88.0
    # Submitting a blank field clears it.
    client.post(f"/assignments/{aid}/grades", data={f"points_{sid}": ""}, follow_redirects=True)
    assert client.get(f"/api/courses/{cid}/students/{sid}/grade").get_json()["categories"]["homework"]["percentage"] is None
