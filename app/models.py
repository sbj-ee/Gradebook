from werkzeug.security import generate_password_hash

from .db import get_db
from .utils import (
    CATEGORIES,
    category_percentage,
    letter_grade,
    parse_weights,
    weighted_final,
)


class WeightError(Exception):
    """Raised when a course's category weights do not add up to 100."""


def unique_violation_message(exc):
    """Map a SQLite UNIQUE-constraint error to a friendly, field-specific message."""
    msg = str(exc).lower()
    if "user.email" in msg:
        return "that email is already in use"
    if "user.phone" in msg:
        return "that phone number is already in use"
    if "user.username" in msg:
        return "that username is already taken"
    return "that username, email, or phone is already in use"


# --- Courses ---------------------------------------------------------------

def list_courses():
    db = get_db()
    return db.execute(
        "SELECT * FROM course ORDER BY name COLLATE NOCASE"
    ).fetchall()


def get_course(course_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM course WHERE id = ?", (course_id,)
    ).fetchone()


def list_courses_for_user(user_id):
    db = get_db()
    return db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM student s WHERE s.course_id = c.id) AS student_count
             FROM course c
            WHERE c.created_by = ?
         ORDER BY c.name COLLATE NOCASE""",
        (user_id,),
    ).fetchall()


def _validate_weights(homework, quiz, exam):
    """Coerce and check the three weights; raise WeightError unless they total 100."""
    homework, quiz, exam = parse_weights(homework, quiz, exam)
    if min(homework, quiz, exam) < 0:
        raise WeightError("weights cannot be negative")
    if homework + quiz + exam != 100:
        raise WeightError("homework, quiz, and exam weights must add up to 100")
    return homework, quiz, exam


def create_course(name, description, term, homework_weight, quiz_weight, exam_weight, created_by):
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    homework_weight, quiz_weight, exam_weight = _validate_weights(
        homework_weight, quiz_weight, exam_weight
    )
    db = get_db()
    cur = db.execute(
        """INSERT INTO course
             (name, description, term, homework_weight, quiz_weight, exam_weight, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            (description or "").strip(),
            (term or "").strip(),
            homework_weight,
            quiz_weight,
            exam_weight,
            created_by,
        ),
    )
    db.commit()
    return cur.lastrowid


def update_course(course_id, name, description, term, homework_weight, quiz_weight, exam_weight):
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    homework_weight, quiz_weight, exam_weight = _validate_weights(
        homework_weight, quiz_weight, exam_weight
    )
    db = get_db()
    db.execute(
        """UPDATE course
              SET name = ?, description = ?, term = ?,
                  homework_weight = ?, quiz_weight = ?, exam_weight = ?
            WHERE id = ?""",
        (
            name,
            (description or "").strip(),
            (term or "").strip(),
            homework_weight,
            quiz_weight,
            exam_weight,
            course_id,
        ),
    )
    db.commit()


def delete_course(course_id):
    # student / assignment / grade rows cascade via ON DELETE CASCADE.
    db = get_db()
    db.execute("DELETE FROM course WHERE id = ?", (course_id,))
    db.commit()


# --- Students --------------------------------------------------------------

def list_students(course_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM student WHERE course_id = ? ORDER BY name COLLATE NOCASE",
        (course_id,),
    ).fetchall()


def get_student(student_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM student WHERE id = ?", (student_id,)
    ).fetchone()


def create_student(course_id, student_code, name, email=None, phone=None):
    """Enroll a student. ``student_code`` is the visible student ID, unique within
    the course. Raises ValueError on blank input or a duplicate student ID."""
    if get_course(course_id) is None:
        raise ValueError("course not found")
    student_code = (student_code or "").strip()
    if not student_code:
        raise ValueError("student ID is required")
    name = (name or "").strip()
    if not name:
        raise ValueError("student name is required")
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO student (course_id, student_id, name, email, phone) VALUES (?, ?, ?, ?, ?)",
            (course_id, student_code, name,
             (email or "").strip() or None, (phone or "").strip() or None),
        )
        db.commit()
    except db.IntegrityError:
        raise ValueError(f"student ID {student_code!r} is already used in this course")
    return cur.lastrowid


def update_student(student_id, student_code, name, email=None, phone=None):
    """Update a student row. ``student_id`` is the primary key; ``student_code`` is
    the visible student ID. Raises ValueError on blank input or a duplicate ID."""
    student_code = (student_code or "").strip()
    if not student_code:
        raise ValueError("student ID is required")
    name = (name or "").strip()
    if not name:
        raise ValueError("student name is required")
    db = get_db()
    try:
        db.execute(
            "UPDATE student SET student_id = ?, name = ?, email = ?, phone = ? WHERE id = ?",
            (student_code, name,
             (email or "").strip() or None, (phone or "").strip() or None, student_id),
        )
        db.commit()
    except db.IntegrityError:
        raise ValueError(f"student ID {student_code!r} is already used in this course")


def delete_student(student_id):
    # grade rows cascade via ON DELETE CASCADE.
    db = get_db()
    db.execute("DELETE FROM student WHERE id = ?", (student_id,))
    db.commit()


# --- Assignments -----------------------------------------------------------

def list_assignments(course_id):
    """Assignments for a course, grouped by category order then name."""
    db = get_db()
    return db.execute(
        """SELECT * FROM assignment
            WHERE course_id = ?
         ORDER BY CASE category WHEN 'homework' THEN 0 WHEN 'quiz' THEN 1
                                WHEN 'exam' THEN 2 ELSE 3 END,
                  name COLLATE NOCASE""",
        (course_id,),
    ).fetchall()


def get_assignment(assignment_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM assignment WHERE id = ?", (assignment_id,)
    ).fetchone()


def _parse_max_points(value):
    try:
        points = float(value)
    except (TypeError, ValueError):
        raise ValueError("max points must be a number")
    if points <= 0:
        raise ValueError("max points must be greater than zero")
    return points


def create_assignment(course_id, category, name, max_points, extra_credit=False):
    if get_course(course_id) is None:
        raise ValueError("course not found")
    category = (category or "").strip().lower()
    if category not in CATEGORIES:
        raise ValueError("category must be homework, quiz, or exam")
    name = (name or "").strip()
    if not name:
        raise ValueError("assignment name is required")
    max_points = _parse_max_points(max_points)
    db = get_db()
    cur = db.execute(
        "INSERT INTO assignment (course_id, category, name, max_points, extra_credit) "
        "VALUES (?, ?, ?, ?, ?)",
        (course_id, category, name, max_points, 1 if extra_credit else 0),
    )
    db.commit()
    return cur.lastrowid


def update_assignment(assignment_id, category, name, max_points, extra_credit=False):
    category = (category or "").strip().lower()
    if category not in CATEGORIES:
        raise ValueError("category must be homework, quiz, or exam")
    name = (name or "").strip()
    if not name:
        raise ValueError("assignment name is required")
    max_points = _parse_max_points(max_points)
    db = get_db()
    # Don't let a lowered maximum strand an already-recorded grade above it; that
    # would break the same 0..max invariant set_grade enforces.
    highest = db.execute(
        "SELECT MAX(points) AS m FROM grade WHERE assignment_id = ?", (assignment_id,)
    ).fetchone()["m"]
    if highest is not None and max_points < highest:
        raise ValueError(
            f"max points cannot be below an existing grade of {highest:g}"
        )
    db.execute(
        "UPDATE assignment SET category = ?, name = ?, max_points = ?, extra_credit = ? "
        "WHERE id = ?",
        (category, name, max_points, 1 if extra_credit else 0, assignment_id),
    )
    db.commit()


def delete_assignment(assignment_id):
    # grade rows cascade via ON DELETE CASCADE.
    db = get_db()
    db.execute("DELETE FROM assignment WHERE id = ?", (assignment_id,))
    db.commit()


# --- Grades ----------------------------------------------------------------

def get_grade(assignment_id, student_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM grade WHERE assignment_id = ? AND student_id = ?",
        (assignment_id, student_id),
    ).fetchone()


def set_grade(assignment_id, student_id, points):
    """Record (or update) a student's score on an assignment.

    Raises ValueError on a missing assignment/student, a course mismatch, or a
    score outside ``0..max_points``. Returns the grade row id.
    """
    assignment = get_assignment(assignment_id)
    if assignment is None:
        raise ValueError("assignment not found")
    student = get_student(student_id)
    if student is None:
        raise ValueError("student not found")
    if student["course_id"] != assignment["course_id"]:
        raise ValueError("student and assignment belong to different courses")
    try:
        points = float(points)
    except (TypeError, ValueError):
        raise ValueError("points must be a number")
    if points < 0:
        raise ValueError("points cannot be negative")
    if points > assignment["max_points"]:
        raise ValueError(
            f"points cannot exceed the maximum of {assignment['max_points']:g}"
        )
    db = get_db()
    db.execute(
        """INSERT INTO grade (assignment_id, student_id, points)
           VALUES (?, ?, ?)
           ON CONFLICT(assignment_id, student_id)
           DO UPDATE SET points = excluded.points""",
        (assignment_id, student_id, points),
    )
    db.commit()
    return get_grade(assignment_id, student_id)["id"]


def clear_grade(assignment_id, student_id):
    db = get_db()
    db.execute(
        "DELETE FROM grade WHERE assignment_id = ? AND student_id = ?",
        (assignment_id, student_id),
    )
    db.commit()


def _course_weights(course):
    return {
        "homework": course["homework_weight"],
        "quiz": course["quiz_weight"],
        "exam": course["exam_weight"],
    }


def student_grade(student_id):
    """Computed grade summary for one student: per-category percentages, the
    weighted final, and a letter. Returns None if the student doesn't exist."""
    student = get_student(student_id)
    if student is None:
        return None
    course = get_course(student["course_id"])
    assignments = list_assignments(course["id"])
    db = get_db()
    grades = {
        r["assignment_id"]: r["points"]
        for r in db.execute(
            "SELECT assignment_id, points FROM grade WHERE student_id = ?",
            (student_id,),
        ).fetchall()
    }
    return _summarize(student, assignments, grades, _course_weights(course))


def _summarize(student, assignments, grades, weights):
    """Build a student's grade summary from in-memory rows (no further queries)."""
    categories = {}
    for category in CATEGORIES:
        earned = possible = 0.0
        for a in assignments:
            if a["category"] != category:
                continue
            points = grades.get(a["id"])
            if points is None:
                continue
            earned += points
            # Extra-credit work boosts the numerator but not the possible total,
            # so it can lift a category's percentage (potentially past 100%).
            if not a["extra_credit"]:
                possible += a["max_points"]
        categories[category] = {
            "earned": earned,
            "possible": possible,
            "pct": category_percentage(earned, possible),
        }
    pcts = {cat: categories[cat]["pct"] for cat in CATEGORIES}
    final = weighted_final(pcts, weights)
    return {
        "student": student,
        "grades": grades,
        "categories": categories,
        "final": final,
        "letter": letter_grade(final),
    }


def course_gradebook(course_id):
    """Everything the gradebook grid needs for a course: the course, its
    assignments, and each student's grades + computed totals. Returns None when
    the course doesn't exist."""
    course = get_course(course_id)
    if course is None:
        return None
    students = list_students(course_id)
    assignments = list_assignments(course_id)
    weights = _course_weights(course)
    db = get_db()
    grade_rows = db.execute(
        """SELECT g.student_id, g.assignment_id, g.points
             FROM grade g JOIN assignment a ON a.id = g.assignment_id
            WHERE a.course_id = ?""",
        (course_id,),
    ).fetchall()
    by_student = {}
    for r in grade_rows:
        by_student.setdefault(r["student_id"], {})[r["assignment_id"]] = r["points"]
    rows = [
        _summarize(s, assignments, by_student.get(s["id"], {}), weights)
        for s in students
    ]
    return {
        "course": course,
        "assignments": assignments,
        "weights": weights,
        "rows": rows,
    }


def grade_snapshot(grade_id):
    """A grade joined with assignment, course, and student contact info.

    Used to build notification messages; capture it before deleting a grade.
    """
    db = get_db()
    return db.execute(
        """SELECT g.*, a.name AS assignment_name, a.category, a.max_points,
                  a.course_id, c.name AS course_name,
                  s.student_id AS student_code, s.name AS student_name,
                  s.email AS student_email, s.phone AS student_phone
             FROM grade g
             JOIN assignment a ON a.id = g.assignment_id
             JOIN course c ON c.id = a.course_id
             JOIN student s ON s.id = g.student_id
            WHERE g.id = ?""",
        (grade_id,),
    ).fetchone()


# --- Reporting -------------------------------------------------------------

def query_grades(course_id=None, category=None):
    """All grades joined with course / assignment / student, with optional filters.

    Used by the CSV export. Invalid/blank filters are ignored rather than raising.
    """
    sql = [
        """SELECT c.id AS course_id, c.name AS course_name,
                  s.student_id AS student_id, s.name AS student_name,
                  a.category, a.name AS assignment_name,
                  a.max_points, a.extra_credit, g.points, g.created_at
             FROM grade g
             JOIN assignment a ON a.id = g.assignment_id
             JOIN course c ON c.id = a.course_id
             JOIN student s ON s.id = g.student_id
            WHERE 1 = 1"""
    ]
    params = []
    if course_id:
        sql.append("AND c.id = ?")
        params.append(course_id)
    if category in CATEGORIES:
        sql.append("AND a.category = ?")
        params.append(category)
    sql.append(
        "ORDER BY c.name COLLATE NOCASE, s.name COLLATE NOCASE, a.name COLLATE NOCASE"
    )
    return get_db().execute("\n".join(sql), params).fetchall()


# --- Users (admin) ---------------------------------------------------------

def get_user(user_id):
    db = get_db()
    return db.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()


def record_login(user_id):
    """Stamp the user's last login with the current UTC time."""
    db = get_db()
    db.execute(
        "UPDATE user SET last_login_at = datetime('now') WHERE id = ?", (user_id,)
    )
    db.commit()


def list_users():
    db = get_db()
    return db.execute(
        """SELECT u.*, COUNT(c.id) AS course_count
             FROM user u
             LEFT JOIN course c ON c.created_by = u.id
         GROUP BY u.id
         ORDER BY u.username COLLATE NOCASE"""
    ).fetchall()


def set_user_admin(user_id, is_admin):
    db = get_db()
    db.execute(
        "UPDATE user SET is_admin = ? WHERE id = ?",
        (1 if is_admin else 0, user_id),
    )
    db.commit()


def create_user(username, password_hash, email=None, phone=None):
    """Insert a user. Raises ValueError on a blank or non-unique field."""
    username = (username or "").strip()
    if not username:
        raise ValueError("username is required")
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO user (username, password_hash, email, phone) VALUES (?, ?, ?, ?)",
            (username, password_hash, (email or "").strip() or None, (phone or "").strip() or None),
        )
        db.commit()
        return cur.lastrowid
    except db.IntegrityError as e:
        raise ValueError(unique_violation_message(e))


def update_user_account(user_id, username, email, phone):
    """Admin edit of a user's username + contact info. Raises ValueError on a
    blank or non-unique field."""
    username = (username or "").strip()
    if not username:
        raise ValueError("username is required")
    db = get_db()
    try:
        db.execute(
            "UPDATE user SET username = ?, email = ?, phone = ? WHERE id = ?",
            (username, (email or "").strip() or None, (phone or "").strip() or None, user_id),
        )
        db.commit()
    except db.IntegrityError as e:
        raise ValueError(unique_violation_message(e))


def update_contact(user_id, email, phone):
    """Self-service update of a user's own email / phone. Raises ValueError if the
    email or phone is already used by another account."""
    db = get_db()
    try:
        db.execute(
            "UPDATE user SET email = ?, phone = ? WHERE id = ?",
            ((email or "").strip() or None, (phone or "").strip() or None, user_id),
        )
        db.commit()
    except db.IntegrityError as e:
        raise ValueError(unique_violation_message(e))


def set_password(user_id, raw_password):
    if not raw_password:
        raise ValueError("password is required")
    db = get_db()
    db.execute(
        "UPDATE user SET password_hash = ? WHERE id = ?",
        (generate_password_hash(raw_password), user_id),
    )
    db.commit()


def delete_user(user_id):
    """Delete a user and detach any courses they created."""
    db = get_db()
    db.execute("UPDATE course SET created_by = NULL WHERE created_by = ?", (user_id,))
    db.execute("DELETE FROM user WHERE id = ?", (user_id,))
    db.commit()


def counts():
    db = get_db()
    return {
        "users": db.execute("SELECT COUNT(*) AS n FROM user").fetchone()["n"],
        "courses": db.execute("SELECT COUNT(*) AS n FROM course").fetchone()["n"],
        "students": db.execute("SELECT COUNT(*) AS n FROM student").fetchone()["n"],
        "assignments": db.execute("SELECT COUNT(*) AS n FROM assignment").fetchone()["n"],
        "grades": db.execute("SELECT COUNT(*) AS n FROM grade").fetchone()["n"],
        "notifications": db.execute("SELECT COUNT(*) AS n FROM notification").fetchone()["n"],
    }


# --- Notifications ---------------------------------------------------------

def record_notification(
    grade_id, student_id, event, channel, recipient, subject, body, status, detail=""
):
    db = get_db()
    db.execute(
        """INSERT INTO notification
             (grade_id, student_id, event, channel, recipient, subject, body, status, detail)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (grade_id, student_id, event, channel, recipient, subject, body, status, detail),
    )
    db.commit()


def list_notifications(limit=100):
    db = get_db()
    return db.execute(
        "SELECT * FROM notification ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()


# --- Password reset --------------------------------------------------------

def find_user_by_identifier(identifier):
    """Find a user by username or email (for password reset requests)."""
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    db = get_db()
    return db.execute(
        "SELECT * FROM user WHERE username = ? OR email = ?", (identifier, identifier)
    ).fetchone()


def create_password_reset(user_id, token_hash, expires_at):
    """Store a reset token (hashed), replacing any unused ones for the user."""
    db = get_db()
    db.execute("DELETE FROM password_reset WHERE user_id = ? AND used = 0", (user_id,))
    db.execute(
        "INSERT INTO password_reset (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
        (user_id, token_hash, expires_at),
    )
    db.commit()


def get_password_reset(token_hash):
    db = get_db()
    return db.execute(
        "SELECT * FROM password_reset WHERE token_hash = ?", (token_hash,)
    ).fetchone()


def mark_reset_used(reset_id):
    db = get_db()
    db.execute("UPDATE password_reset SET used = 1 WHERE id = ?", (reset_id,))
    db.commit()
