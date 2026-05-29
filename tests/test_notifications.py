from tests.conftest import add_assignment, add_student, make_course


def test_grade_with_email_is_logged(client, auth, notifications):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid, email="pat@example.com")
    aid = add_assignment(client, cid, max_points=100)
    client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 80})
    rows = notifications()
    assert len(rows) == 1
    assert rows[0]["channel"] == "email"
    assert rows[0]["event"] == "posted"
    # No SMTP configured in tests -> the message is logged, not sent.
    assert rows[0]["status"] == "logged"
    assert rows[0]["recipient"] == "pat@example.com"


def test_grade_without_contact_is_skipped(client, auth, notifications):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid)  # no email/phone
    aid = add_assignment(client, cid, max_points=100)
    client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 80})
    rows = notifications()
    assert len(rows) == 1
    assert rows[0]["status"] == "skipped"


def test_grade_update_emits_updated_event(client, auth, notifications):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid, email="pat@example.com", phone="+15551230000")
    aid = add_assignment(client, cid, max_points=100)
    client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 50})
    client.post(f"/api/assignments/{aid}/grades", json={"student_id": sid, "points": 60})
    events = [r["event"] for r in notifications()]
    # Two channels (email + sms) per event, across a 'posted' then 'updated'.
    assert events.count("posted") == 2
    assert events.count("updated") == 2


def test_web_clear_grade_emits_removed(client, auth, notifications):
    auth.register()
    cid = make_course(client)
    sid = add_student(client, cid, email="pat@example.com")
    aid = add_assignment(client, cid, max_points=100)
    client.post(f"/assignments/{aid}/grades", data={f"points_{sid}": "70"}, follow_redirects=True)
    client.post(f"/assignments/{aid}/grades", data={f"points_{sid}": ""}, follow_redirects=True)
    events = [r["event"] for r in notifications()]
    assert "posted" in events
    assert "removed" in events
