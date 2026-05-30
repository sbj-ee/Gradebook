from flask import Blueprint, g, jsonify, request

from . import models
from .auth import api_auth_required
from .notifications import notify_grade_event

bp = Blueprint("api", __name__, url_prefix="/api")


def course_json(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "term": row["term"],
        "weights": {
            "homework": row["homework_weight"],
            "quiz": row["quiz_weight"],
            "exam": row["exam_weight"],
        },
        "created_by": row["created_by"],
        "created_at": row["created_at"],
    }


def student_json(row):
    return {
        "id": row["id"],
        "student_id": row["student_id"],
        "name": row["name"],
        "email": row["email"],
        "phone": row["phone"],
        "created_at": row["created_at"],
    }


def assignment_json(row):
    return {
        "id": row["id"],
        "course_id": row["course_id"],
        "category": row["category"],
        "name": row["name"],
        "max_points": row["max_points"],
        "extra_credit": bool(row["extra_credit"]),
        "created_at": row["created_at"],
    }


def grade_json(row):
    return {
        "id": row["id"],
        "assignment_id": row["assignment_id"],
        "student_id": row["student_id"],
        "points": row["points"],
        "created_at": row["created_at"],
    }


def summary_json(summary):
    """Serialize a computed student grade summary (see models.student_grade)."""
    return {
        "student": student_json(summary["student"]),
        "categories": {
            cat: {
                "earned": vals["earned"],
                "possible": vals["possible"],
                "percentage": vals["pct"],
            }
            for cat, vals in summary["categories"].items()
        },
        "final_percentage": summary["final"],
        "letter": summary["letter"],
    }


def error(message, status):
    resp = jsonify(error=message)
    resp.status_code = status
    return resp


def _require_course_edit(course):
    """Return an error response if the current user can't edit ``course``, else None."""
    if course is None:
        return error("course not found", 404)
    if not (g.user["is_admin"] or course["created_by"] == g.user["id"]):
        return error("forbidden", 403)
    return None


def _teaches_enrolled_course(student_id):
    """True if the current user created any course the student is enrolled in."""
    return any(
        c["created_by"] == g.user["id"]
        for c in models.courses_for_student(student_id)
    )


# --- Courses ---------------------------------------------------------------

@bp.route("/courses", methods=("GET",))
def list_courses():
    return jsonify([course_json(c) for c in models.list_courses()])


@bp.route("/courses", methods=("POST",))
@api_auth_required
def create_course():
    data = request.get_json(silent=True) or {}
    # Default to the schema's 40/20/40 split when weights are omitted.
    weights = data.get("weights") or {}
    try:
        course_id = models.create_course(
            data.get("name"),
            data.get("description", ""),
            data.get("term", ""),
            weights.get("homework", 40),
            weights.get("quiz", 20),
            weights.get("exam", 40),
            g.user["id"],
        )
    except (ValueError, models.WeightError) as e:
        return error(str(e), 400)
    return jsonify(course_json(models.get_course(course_id))), 201


@bp.route("/courses/<int:course_id>", methods=("GET",))
def get_course(course_id):
    course = models.get_course(course_id)
    if course is None:
        return error("course not found", 404)
    data = course_json(course)
    data["students"] = [student_json(s) for s in models.list_students(course_id)]
    data["assignments"] = [
        assignment_json(a) for a in models.list_assignments(course_id)
    ]
    return jsonify(data)


@bp.route("/courses/<int:course_id>/gradebook", methods=("GET",))
def course_gradebook(course_id):
    book = models.course_gradebook(course_id)
    if book is None:
        return error("course not found", 404)
    return jsonify(
        {
            "course": course_json(book["course"]),
            "assignments": [assignment_json(a) for a in book["assignments"]],
            "students": [summary_json(row) for row in book["rows"]],
        }
    )


# --- Students --------------------------------------------------------------

@bp.route("/courses/<int:course_id>/students", methods=("GET",))
def list_students(course_id):
    if models.get_course(course_id) is None:
        return error("course not found", 404)
    return jsonify([student_json(s) for s in models.list_students(course_id)])


@bp.route("/courses/<int:course_id>/students", methods=("POST",))
@api_auth_required
def create_student(course_id):
    denied = _require_course_edit(models.get_course(course_id))
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    try:
        student_id = models.create_student(
            course_id,
            data.get("student_id"),
            data.get("name"),
            data.get("email"),
            data.get("phone"),
        )
    except ValueError as e:
        return error(str(e), 400)
    return jsonify(student_json(models.get_student(student_id))), 201


@bp.route("/students/<int:student_id>", methods=("PUT",))
@api_auth_required
def update_student(student_id):
    student = models.get_student(student_id)
    if student is None:
        return error("student not found", 404)
    # Editing the global student record requires editing a course they're in.
    if not (g.user["is_admin"] or _teaches_enrolled_course(student_id)):
        return error("forbidden", 403)
    data = request.get_json(silent=True) or {}
    try:
        models.update_student(
            student_id,
            data.get("student_id", student["student_id"]),
            data.get("name", student["name"]),
            data.get("email", student["email"]),
            data.get("phone", student["phone"]),
        )
    except ValueError as e:
        return error(str(e), 400)
    return jsonify(student_json(models.get_student(student_id)))


@bp.route("/courses/<int:course_id>/students/<int:student_id>/grade", methods=("GET",))
def student_grade(course_id, student_id):
    summary = models.student_grade(course_id, student_id)
    if summary is None:
        return error("student not enrolled in this course", 404)
    return jsonify(summary_json(summary))


# --- Assignments -----------------------------------------------------------

@bp.route("/courses/<int:course_id>/assignments", methods=("GET",))
def list_assignments(course_id):
    if models.get_course(course_id) is None:
        return error("course not found", 404)
    return jsonify([assignment_json(a) for a in models.list_assignments(course_id)])


@bp.route("/courses/<int:course_id>/assignments", methods=("POST",))
@api_auth_required
def create_assignment(course_id):
    denied = _require_course_edit(models.get_course(course_id))
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    try:
        assignment_id = models.create_assignment(
            course_id,
            data.get("category"),
            data.get("name"),
            data.get("max_points"),
            data.get("extra_credit", False),
        )
    except ValueError as e:
        return error(str(e), 400)
    return jsonify(assignment_json(models.get_assignment(assignment_id))), 201


@bp.route("/assignments/<int:assignment_id>", methods=("PUT",))
@api_auth_required
def update_assignment(assignment_id):
    assignment = models.get_assignment(assignment_id)
    if assignment is None:
        return error("assignment not found", 404)
    denied = _require_course_edit(models.get_course(assignment["course_id"]))
    if denied:
        return denied
    # Omitted fields keep their current value, so partial updates work.
    data = request.get_json(silent=True) or {}
    try:
        models.update_assignment(
            assignment_id,
            data.get("category", assignment["category"]),
            data.get("name", assignment["name"]),
            data.get("max_points", assignment["max_points"]),
            data.get("extra_credit", assignment["extra_credit"]),
        )
    except ValueError as e:
        return error(str(e), 400)
    return jsonify(assignment_json(models.get_assignment(assignment_id)))


# --- Grades ----------------------------------------------------------------

@bp.route("/assignments/<int:assignment_id>/grades", methods=("POST",))
@api_auth_required
def set_grade(assignment_id):
    assignment = models.get_assignment(assignment_id)
    if assignment is None:
        return error("assignment not found", 404)
    denied = _require_course_edit(models.get_course(assignment["course_id"]))
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    existing = (
        models.get_grade(assignment_id, data.get("student_id"))
        if data.get("student_id")
        else None
    )
    try:
        grade_id = models.set_grade(
            assignment_id, data.get("student_id"), data.get("points")
        )
    except ValueError as e:
        return error(str(e), 400)
    event = "updated" if existing is not None else "posted"
    notify_grade_event(event, models.grade_snapshot(grade_id))
    status = 200 if existing is not None else 201
    return jsonify(grade_json(models.get_grade(assignment_id, data.get("student_id")))), status
