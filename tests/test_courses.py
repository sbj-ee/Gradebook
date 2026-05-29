from tests.conftest import basic_auth_header


def test_create_course_success(client, auth):
    auth.register()
    resp = client.post(
        "/api/courses",
        json={"name": "Biology", "term": "Fall 2026",
              "weights": {"homework": 50, "quiz": 20, "exam": 30}},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["name"] == "Biology"
    assert body["weights"] == {"homework": 50, "quiz": 20, "exam": 30}


def test_create_course_default_weights(client, auth):
    auth.register()
    # No weights provided -> schema defaults (40/20/40).
    body = client.post("/api/courses", json={"name": "History"}).get_json()
    assert body["weights"] == {"homework": 40, "quiz": 20, "exam": 40}


def test_weights_must_sum_to_100(client, auth):
    auth.register()
    resp = client.post(
        "/api/courses",
        json={"name": "Bad", "weights": {"homework": 50, "quiz": 20, "exam": 40}},
    )
    assert resp.status_code == 400
    assert b"100" in resp.data


def test_negative_weight_rejected(client, auth):
    auth.register()
    resp = client.post(
        "/api/courses",
        json={"name": "Bad", "weights": {"homework": -10, "quiz": 60, "exam": 50}},
    )
    assert resp.status_code == 400


def test_create_course_requires_auth(client):
    resp = client.post("/api/courses", json={"name": "Nope"})
    assert resp.status_code == 401


def test_basic_auth_create_course(client, auth):
    auth.register()
    auth.logout()
    resp = client.post(
        "/api/courses", json={"name": "Chem"}, headers=basic_auth_header()
    )
    assert resp.status_code == 201


def test_list_courses_public(client, auth):
    auth.register()
    client.post("/api/courses", json={"name": "Public Course"})
    auth.logout()
    resp = client.get("/api/courses")
    assert resp.status_code == 200
    assert any(c["name"] == "Public Course" for c in resp.get_json())


def test_course_detail_includes_students_and_assignments(client, auth):
    auth.register()
    cid = client.post("/api/courses", json={"name": "C"}).get_json()["id"]
    client.post(f"/api/courses/{cid}/students", json={"student_id": "S1", "name": "Pat"})
    client.post(
        f"/api/courses/{cid}/assignments",
        json={"category": "exam", "name": "Midterm", "max_points": 50},
    )
    data = client.get(f"/api/courses/{cid}").get_json()
    assert len(data["students"]) == 1
    assert data["assignments"][0]["name"] == "Midterm"
