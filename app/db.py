import sqlite3

import click
from flask import current_app, g
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))


def init_db_if_needed():
    db = get_db()
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='user'"
    ).fetchone()
    if row is None:
        init_db()
    else:
        _migrate(db)


def _migrate(db):
    """Apply small, idempotent schema changes to a pre-existing database."""
    columns = {r["name"] for r in db.execute("PRAGMA table_info(user)").fetchall()}
    if "is_admin" not in columns:
        db.execute("ALTER TABLE user ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    if "email" not in columns:
        db.execute("ALTER TABLE user ADD COLUMN email TEXT")
    if "phone" not in columns:
        db.execute("ALTER TABLE user ADD COLUMN phone TEXT")
    if "last_login_at" not in columns:
        db.execute("ALTER TABLE user ADD COLUMN last_login_at TEXT")
    # Extra-credit flag added to assignments after the initial release.
    acols = {r["name"] for r in db.execute("PRAGMA table_info(assignment)").fetchall()}
    if acols and "extra_credit" not in acols:
        db.execute(
            "ALTER TABLE assignment ADD COLUMN extra_credit INTEGER NOT NULL DEFAULT 0"
        )
    # Grading scale + drop-lowest options added to courses after release.
    ccols = {r["name"] for r in db.execute("PRAGMA table_info(course)").fetchall()}
    if ccols and "grading_scale" not in ccols:
        db.execute(
            "ALTER TABLE course ADD COLUMN grading_scale TEXT NOT NULL DEFAULT 'standard'"
        )
    for cat in ("homework", "quiz", "exam"):
        col = f"drop_lowest_{cat}"
        if ccols and col not in ccols:
            db.execute(
                f"ALTER TABLE course ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0"
            )
    # Split the original per-course student table into a global student record plus
    # an enrollment join, so one student can belong to several courses.
    scols = {r["name"] for r in db.execute("PRAGMA table_info(student)").fetchall()}
    has_enrollment = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='enrollment'"
    ).fetchone()
    if scols and "course_id" in scols and has_enrollment is None:
        _split_students_to_enrollment(db)
    # Enforce unique email/phone (NULLs allowed). On a pre-existing database that
    # already holds duplicates, the index can't be built — log and carry on rather
    # than failing startup.
    for col in ("email", "phone"):
        try:
            db.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS idx_user_{col} ON user ({col})"
            )
        except sqlite3.Error:
            current_app.logger.warning(
                "could not add unique index on user.%s (existing duplicates?)", col
            )
    db.execute(
        """CREATE TABLE IF NOT EXISTS notification (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             grade_id INTEGER,
             student_id INTEGER,
             event TEXT NOT NULL,
             channel TEXT NOT NULL,
             recipient TEXT NOT NULL DEFAULT '',
             subject TEXT NOT NULL DEFAULT '',
             body TEXT NOT NULL DEFAULT '',
             status TEXT NOT NULL,
             detail TEXT NOT NULL DEFAULT '',
             created_at TEXT NOT NULL DEFAULT (datetime('now'))
           )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS password_reset (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER NOT NULL,
             token_hash TEXT NOT NULL,
             expires_at TEXT NOT NULL,
             used INTEGER NOT NULL DEFAULT 0,
             created_at TEXT NOT NULL DEFAULT (datetime('now'))
           )"""
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_password_reset_token ON password_reset (token_hash)"
    )
    db.commit()


def _split_students_to_enrollment(db):
    """One-time migration: rebuild the per-course ``student`` table as a global
    ``student`` record (deduplicated by visible student ID) plus an ``enrollment``
    join, remapping grade rows to the new student ids."""
    db.executescript(
        """
        CREATE TABLE student_new (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          student_id TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL,
          email TEXT,
          phone TEXT,
          created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE enrollment (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          course_id INTEGER NOT NULL,
          student_id INTEGER NOT NULL,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          UNIQUE (course_id, student_id),
          FOREIGN KEY (course_id) REFERENCES course (id) ON DELETE CASCADE,
          FOREIGN KEY (student_id) REFERENCES student_new (id) ON DELETE CASCADE
        );
        """
    )
    # One global student per distinct visible ID (first occurrence wins).
    db.execute(
        """INSERT INTO student_new (student_id, name, email, phone, created_at)
           SELECT student_id, name, email, phone, MIN(created_at)
             FROM student GROUP BY student_id"""
    )
    # An enrollment for every original (course, student) row.
    db.execute(
        """INSERT OR IGNORE INTO enrollment (course_id, student_id)
           SELECT s.course_id, sn.id
             FROM student s JOIN student_new sn ON sn.student_id = s.student_id"""
    )
    # Remap grades to the new student ids by matching the visible code (done while
    # the old table still exists, as a single set-based update — no double remap).
    db.execute(
        """UPDATE grade SET student_id = (
               SELECT sn.id FROM student so
               JOIN student_new sn ON sn.student_id = so.student_id
               WHERE so.id = grade.student_id)"""
    )
    db.executescript(
        "DROP TABLE student; ALTER TABLE student_new RENAME TO student;"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_enrollment_course ON enrollment (course_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_enrollment_student ON enrollment (student_id)"
    )
    db.commit()


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Clear existing data and create new tables."""
    init_db()
    click.echo("Initialized the database.")


@click.command("create-admin")
@click.argument("username")
@click.argument("password")
@with_appcontext
def create_admin_command(username, password):
    """Create a new user with admin privileges."""
    db = get_db()
    try:
        db.execute(
            "INSERT INTO user (username, password_hash, is_admin) VALUES (?, ?, 1)",
            (username, generate_password_hash(password)),
        )
        db.commit()
    except db.IntegrityError:
        raise click.ClickException(f"User {username!r} already exists.") from None
    click.echo(f"Created admin {username!r}.")


@click.command("set-admin")
@click.argument("username")
@click.option("--remove", is_flag=True, help="Revoke admin instead of granting it.")
@with_appcontext
def set_admin_command(username, remove):
    """Grant (or, with --remove, revoke) admin on an existing user."""
    db = get_db()
    cur = db.execute(
        "UPDATE user SET is_admin = ? WHERE username = ?",
        (0 if remove else 1, username),
    )
    db.commit()
    if cur.rowcount == 0:
        raise click.ClickException(f"No user named {username!r}.")
    verb = "Revoked admin from" if remove else "Granted admin to"
    click.echo(f"{verb} {username!r}.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_admin_command)
    app.cli.add_command(set_admin_command)
