from tests.conftest import add_assignment, add_student


def _course(client, **extra):
    payload = {"name": "C", "weights": {"homework": 100, "quiz": 0, "exam": 0}}
    payload.update(extra)
    return client.post("/api/courses", json=payload).get_json()["id"]


def test_course_json_exposes_scale_and_drops(client, auth):
    auth.register()
    cid = _course(client, grading_scale="plus_minus",
                  drop_lowest={"homework": 1, "quiz": 0, "exam": 0})
    course = client.get(f"/api/courses/{cid}").get_json()
    assert course["grading_scale"] == "plus_minus"
    assert course["drop_lowest"]["homework"] == 1


def test_invalid_scale_rejected(client, auth):
    auth.register()
    resp = client.post("/api/courses", json={"name": "X", "grading_scale": "bogus"})
    assert resp.status_code == 400


def test_drop_lowest_homework(client, auth):
    auth.register()
    cid = _course(client, drop_lowest={"homework": 1, "quiz": 0, "exam": 0})
    sid = add_student(client, cid)
    a = [add_assignment(client, cid, category="homework", name=f"HW{i}", max_points=10)
         for i in range(3)]
    # Scores 50%, 80%, 100% -> drop the 50%, keep (8+10)/(10+10) = 90%.
    for aid, pts in zip(a, (5, 8, 10)):
        client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": pts})
    summary = client.get(f"/api/courses/{cid}/students/{sid}/grade").get_json()
    assert summary["categories"]["homework"]["percentage"] == 90.0
    assert summary["final_percentage"] == 90.0


def test_drop_lowest_ignores_extra_credit(client, auth):
    auth.register()
    cid = _course(client, drop_lowest={"homework": 1, "quiz": 0, "exam": 0})
    sid = add_student(client, cid)
    hw1 = add_assignment(client, cid, category="homework", name="HW1", max_points=10)
    hw2 = add_assignment(client, cid, category="homework", name="HW2", max_points=10)
    ec = client.post(
        f"/api/courses/{cid}/assignments",
        json={"category": "homework", "name": "Bonus", "max_points": 5, "extra_credit": True},
    ).get_json()["id"]
    client.post(f"/api/assignments/{hw1}/grades", json={"student_id": sid, "points": 6})   # 60%
    client.post(f"/api/assignments/{hw2}/grades", json={"student_id": sid, "points": 10})  # 100%
    client.post(f"/api/assignments/{ec}/grades", json={"student_id": sid, "points": 2})    # +2 EC
    # Drop the 60% regular; keep HW2 (10/10) + EC 2 -> 12/10 = 120%.
    summary = client.get(f"/api/courses/{cid}/students/{sid}/grade").get_json()
    assert summary["categories"]["homework"]["percentage"] == 120.0


def test_plus_minus_scale_letter(client, auth):
    auth.register()
    cid = client.post(
        "/api/courses",
        json={"name": "C", "weights": {"homework": 0, "quiz": 0, "exam": 100},
              "grading_scale": "plus_minus"},
    ).get_json()["id"]
    sid = add_student(client, cid)
    ex = add_assignment(client, cid, category="exam", name="Final", max_points=100)
    client.post(f"/api/assignments/{ex}/grades", json={"student_id": sid, "points": 91})
    book = client.get(f"/api/courses/{cid}/gradebook").get_json()
    assert book["students"][0]["final_percentage"] == 91.0
    assert book["students"][0]["letter"] == "A-"
