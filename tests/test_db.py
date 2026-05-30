from app.db import get_db, init_db


def test_init_db_is_rerunnable(app):
    # The app fixture already created the schema once; running it again must not
    # raise (the DROP order has to handle a populated database).
    with app.app_context():
        init_db()
        init_db()
        tables = {
            r["name"]
            for r in get_db().execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"user", "course", "student", "enrollment", "assignment", "grade"} <= tables
