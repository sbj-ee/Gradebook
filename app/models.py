from werkzeug.security import generate_password_hash

from .db import get_db
from .utils import (
    CATEGORIES,
    CATEGORY_LABELS,
    GRADING_SCALES,
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
                  (SELECT COUNT(*) FROM enrollment e WHERE e.course_id = c.id) AS student_count
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


def _validate_scale(grading_scale):
    grading_scale = (grading_scale or "standard").strip().lower()
    if grading_scale not in GRADING_SCALES:
        raise ValueError("invalid grading scale")
    return grading_scale


def _validate_drops(drops):
    """Coerce the per-category drop-lowest counts to non-negative ints."""
    drops = drops or {}
    result = {}
    for cat in CATEGORIES:
        try:
            n = int(drops.get(cat, 0) or 0)
        except (TypeError, ValueError):
            raise ValueError("drop-lowest counts must be whole numbers")
        if n < 0:
            raise ValueError("drop-lowest counts cannot be negative")
        result[cat] = n
    return result


def create_course(name, description, term, homework_weight, quiz_weight, exam_weight,
                  created_by, grading_scale="standard", drops=None):
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    homework_weight, quiz_weight, exam_weight = _validate_weights(
        homework_weight, quiz_weight, exam_weight
    )
    grading_scale = _validate_scale(grading_scale)
    drops = _validate_drops(drops)
    db = get_db()
    cur = db.execute(
        """INSERT INTO course
             (name, description, term, homework_weight, quiz_weight, exam_weight,
              grading_scale, drop_lowest_homework, drop_lowest_quiz, drop_lowest_exam,
              created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            (description or "").strip(),
            (term or "").strip(),
            homework_weight,
            quiz_weight,
            exam_weight,
            grading_scale,
            drops["homework"],
            drops["quiz"],
            drops["exam"],
            created_by,
        ),
    )
    db.commit()
    return cur.lastrowid


def update_course(course_id, name, description, term, homework_weight, quiz_weight,
                  exam_weight, grading_scale="standard", drops=None):
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    homework_weight, quiz_weight, exam_weight = _validate_weights(
        homework_weight, quiz_weight, exam_weight
    )
    grading_scale = _validate_scale(grading_scale)
    drops = _validate_drops(drops)
    db = get_db()
    db.execute(
        """UPDATE course
              SET name = ?, description = ?, term = ?,
                  homework_weight = ?, quiz_weight = ?, exam_weight = ?,
                  grading_scale = ?, drop_lowest_homework = ?, drop_lowest_quiz = ?,
                  drop_lowest_exam = ?
            WHERE id = ?""",
        (
            name,
            (description or "").strip(),
            (term or "").strip(),
            homework_weight,
            quiz_weight,
            exam_weight,
            grading_scale,
            drops["homework"],
            drops["quiz"],
            drops["exam"],
            course_id,
        ),
    )
    db.commit()


def delete_course(course_id):
    # student / assignment / grade rows cascade via ON DELETE CASCADE.
    db = get_db()
    db.execute("DELETE FROM course WHERE id = ?", (course_id,))
    db.commit()


# --- Students & enrollment -------------------------------------------------

def list_students(course_id):
    """Students enrolled in a course (global student rows), ordered by name."""
    db = get_db()
    return db.execute(
        """SELECT s.* FROM student s
             JOIN enrollment e ON e.student_id = s.id
            WHERE e.course_id = ?
         ORDER BY s.name COLLATE NOCASE""",
        (course_id,),
    ).fetchall()


def get_student(student_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM student WHERE id = ?", (student_id,)
    ).fetchone()


def get_student_by_code(student_code):
    db = get_db()
    return db.execute(
        "SELECT * FROM student WHERE student_id = ?", (student_code,)
    ).fetchone()


def is_enrolled(course_id, student_id):
    db = get_db()
    return db.execute(
        "SELECT 1 FROM enrollment WHERE course_id = ? AND student_id = ?",
        (course_id, student_id),
    ).fetchone() is not None


def courses_for_student(student_id):
    """Courses a student is enrolled in (id + created_by); used for permission
    checks when editing the shared student record."""
    db = get_db()
    return db.execute(
        """SELECT c.id, c.created_by FROM course c
             JOIN enrollment e ON e.course_id = c.id
            WHERE e.student_id = ?""",
        (student_id,),
    ).fetchall()


def create_student(course_id, student_code, name, email=None, phone=None):
    """Enroll a student in a course, creating the global student on first sight.

    ``student_code`` is the globally-unique visible student ID; if it already
    exists, that student is enrolled and their stored details are left unchanged
    (edit them separately). Raises ValueError on blank input or a duplicate
    enrollment. Returns the student's primary-key id.
    """
    if get_course(course_id) is None:
        raise ValueError("course not found")
    student_code = (student_code or "").strip()
    if not student_code:
        raise ValueError("student ID is required")
    name = (name or "").strip()
    if not name:
        raise ValueError("student name is required")
    db = get_db()
    existing = get_student_by_code(student_code)
    if existing is None:
        cur = db.execute(
            "INSERT INTO student (student_id, name, email, phone) VALUES (?, ?, ?, ?)",
            (student_code, name,
             (email or "").strip() or None, (phone or "").strip() or None),
        )
        student_id = cur.lastrowid
    else:
        student_id = existing["id"]
    try:
        db.execute(
            "INSERT INTO enrollment (course_id, student_id) VALUES (?, ?)",
            (course_id, student_id),
        )
        db.commit()
    except db.IntegrityError:
        db.rollback()
        raise ValueError(
            f"student ID {student_code!r} is already enrolled in this course"
        )
    return student_id


def update_student(student_id, student_code, name, email=None, phone=None):
    """Update the global student record. Raises ValueError on blank input or a
    student ID already used by another student."""
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
        raise ValueError(f"student ID {student_code!r} is already in use")


def unenroll(course_id, student_id):
    """Remove a student from one course: delete their grades on that course's
    assignments and the enrollment row. The global student record stays (they may
    be enrolled in other courses)."""
    db = get_db()
    db.execute(
        """DELETE FROM grade
            WHERE student_id = ?
              AND assignment_id IN (SELECT id FROM assignment WHERE course_id = ?)""",
        (student_id, course_id),
    )
    db.execute(
        "DELETE FROM enrollment WHERE course_id = ? AND student_id = ?",
        (course_id, student_id),
    )
    db.commit()


def delete_student(student_id):
    # Deletes the global student everywhere; enrollment + grade rows cascade.
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
    if not is_enrolled(assignment["course_id"], student_id):
        raise ValueError("student is not enrolled in this assignment's course")
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


def _course_drops(course):
    return {
        "homework": course["drop_lowest_homework"],
        "quiz": course["drop_lowest_quiz"],
        "exam": course["drop_lowest_exam"],
    }


def student_grade(course_id, student_id):
    """Computed grade summary for one student in one course: per-category
    percentages, the weighted final, and a letter. Returns None if the student
    isn't enrolled in the course."""
    student = get_student(student_id)
    if student is None or not is_enrolled(course_id, student_id):
        return None
    course = get_course(course_id)
    assignments = list_assignments(course_id)
    db = get_db()
    grades = {
        r["assignment_id"]: r["points"]
        for r in db.execute(
            """SELECT g.assignment_id, g.points FROM grade g
                 JOIN assignment a ON a.id = g.assignment_id
                WHERE g.student_id = ? AND a.course_id = ?""",
            (student_id, course_id),
        ).fetchall()
    }
    return _summarize(student, assignments, grades, course)


def student_report(course_id, student_id):
    """Detailed per-assignment breakdown for one student in one course, grouped by
    category, marking which scores were dropped. Returns None if not enrolled."""
    student = get_student(student_id)
    if student is None or not is_enrolled(course_id, student_id):
        return None
    course = get_course(course_id)
    assignments = list_assignments(course_id)
    weights = _course_weights(course)
    drops = _course_drops(course)
    db = get_db()
    grades = {
        r["assignment_id"]: r["points"]
        for r in db.execute(
            """SELECT g.assignment_id, g.points FROM grade g
                 JOIN assignment a ON a.id = g.assignment_id
                WHERE g.student_id = ? AND a.course_id = ?""",
            (student_id, course_id),
        ).fetchall()
    }
    pcts = {}
    category_rows = []
    for cat in CATEGORIES:
        items, graded_regular = [], []
        for a in assignments:
            if a["category"] != cat:
                continue
            pts = grades.get(a["id"])
            items.append({
                "id": a["id"],
                "name": a["name"],
                "max_points": a["max_points"],
                "extra_credit": bool(a["extra_credit"]),
                "points": pts,
                "pct": category_percentage(pts, a["max_points"]) if pts is not None else None,
                "dropped": False,
            })
            if pts is not None and not a["extra_credit"]:
                graded_regular.append((pts / a["max_points"], a["id"]))
        n_drop = drops.get(cat, 0)
        dropped_ids = set()
        if n_drop and graded_regular:
            graded_regular.sort(key=lambda t: t[0])
            dropped_ids = {aid for _, aid in graded_regular[:n_drop]}
        earned = possible = 0.0
        for item in items:
            if item["id"] in dropped_ids:
                item["dropped"] = True
                continue
            if item["points"] is None:
                continue
            earned += item["points"]
            if not item["extra_credit"]:
                possible += item["max_points"]
        pct = category_percentage(earned, possible)
        pcts[cat] = pct
        category_rows.append({
            "key": cat,
            "label": CATEGORY_LABELS[cat],
            "weight": weights[cat],
            "drop": n_drop,
            "assignments": items,
            "earned": earned,
            "possible": possible,
            "pct": pct,
        })
    final = weighted_final(pcts, weights)
    return {
        "course": course,
        "student": student,
        "categories": category_rows,
        "final": final,
        "letter": letter_grade(final, course["grading_scale"]),
    }


def _summarize(student, assignments, grades, course):
    """Build a student's grade summary from in-memory rows (no further queries).

    Within each category the N lowest-scoring regular assignments are dropped
    (``drop_lowest_*``); extra-credit work is never dropped and adds to the
    numerator only.
    """
    weights = _course_weights(course)
    drops = _course_drops(course)
    categories = {}
    for category in CATEGORIES:
        regular = []        # (fraction, earned, max) for graded non-EC assignments
        extra_earned = 0.0  # graded extra-credit points
        for a in assignments:
            if a["category"] != category:
                continue
            points = grades.get(a["id"])
            if points is None:
                continue
            if a["extra_credit"]:
                extra_earned += points
            else:
                regular.append((points / a["max_points"], points, a["max_points"]))
        # Drop the lowest-scoring regular assignments for this category.
        n_drop = drops.get(category, 0)
        if n_drop and regular:
            regular.sort(key=lambda t: t[0])
            regular = regular[n_drop:]
        earned = sum(e for _, e, _ in regular) + extra_earned
        possible = sum(m for _, _, m in regular)
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
        "letter": letter_grade(final, course["grading_scale"]),
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
        _summarize(s, assignments, by_student.get(s["id"], {}), course)
        for s in students
    ]
    return {
        "course": course,
        "assignments": assignments,
        "weights": _course_weights(course),
        "drops": _course_drops(course),
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
