import re

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash

from . import importer, models, pdf
from .auth import download_login_required, login_required
from .notifications import notify_grade_event
from .utils import CATEGORIES, CATEGORY_LABELS, GRADING_SCALE_LABELS

bp = Blueprint("web", __name__)


@bp.app_context_processor
def inject_grading_options():
    # Available to every template (course create/edit forms use the scale labels).
    return {
        "categories": CATEGORIES,
        "category_labels": CATEGORY_LABELS,
        "scale_labels": GRADING_SCALE_LABELS,
    }


def _pdf_filename(*parts):
    """Build a safe ASCII download filename from one or more label parts."""
    slug = "-".join(parts)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", slug).strip("-").lower()
    return (slug or "export") + ".pdf"


def _pdf_response(data, filename):
    return Response(
        data,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _can_edit_course(course):
    """A course is editable by an admin or the teacher who created it."""
    return g.user is not None and (
        g.user["is_admin"] or course["created_by"] == g.user["id"]
    )


def _require_course_edit(course):
    if course is None:
        abort(404)
    if not _can_edit_course(course):
        abort(403)


@bp.route("/courses")
def list_courses():
    return render_template("courses/list.html", courses=models.list_courses())


def _drops_from_form():
    return {cat: request.form.get(f"drop_lowest_{cat}") for cat in CATEGORIES}


@bp.route("/courses/new", methods=("GET", "POST"))
@login_required
def new_course():
    if request.method == "POST":
        try:
            course_id = models.create_course(
                request.form.get("name"),
                request.form.get("description"),
                request.form.get("term"),
                request.form.get("homework_weight"),
                request.form.get("quiz_weight"),
                request.form.get("exam_weight"),
                g.user["id"],
                grading_scale=request.form.get("grading_scale"),
                drops=_drops_from_form(),
            )
        except (ValueError, models.WeightError) as e:
            flash(str(e))
            return render_template("courses/new.html", form=request.form)
        flash("Course created.")
        return redirect(url_for("web.course_detail", course_id=course_id))
    return render_template("courses/new.html", form={})


@bp.route("/courses/mine")
@login_required
def my_courses():
    return render_template(
        "courses/mine.html", courses=models.list_courses_for_user(g.user["id"])
    )


@bp.route("/courses/<int:course_id>")
def course_detail(course_id):
    book = models.course_gradebook(course_id)
    if book is None:
        abort(404)
    return render_template(
        "courses/detail.html",
        book=book,
        course=book["course"],
        can_edit=_can_edit_course(book["course"]),
        categories=CATEGORIES,
        category_labels=CATEGORY_LABELS,
    )


@bp.route("/courses/<int:course_id>/edit", methods=("GET", "POST"))
@login_required
def edit_course(course_id):
    course = models.get_course(course_id)
    _require_course_edit(course)
    if request.method == "POST":
        try:
            models.update_course(
                course_id,
                request.form.get("name"),
                request.form.get("description"),
                request.form.get("term"),
                request.form.get("homework_weight"),
                request.form.get("quiz_weight"),
                request.form.get("exam_weight"),
                grading_scale=request.form.get("grading_scale"),
                drops=_drops_from_form(),
            )
            flash("Course updated.")
            return redirect(url_for("web.course_detail", course_id=course_id))
        except (ValueError, models.WeightError) as e:
            flash(str(e))
            return render_template("courses/edit.html", course=course, values=request.form)
    values = {
        "name": course["name"],
        "term": course["term"],
        "description": course["description"],
        "homework_weight": course["homework_weight"],
        "quiz_weight": course["quiz_weight"],
        "exam_weight": course["exam_weight"],
        "grading_scale": course["grading_scale"],
        "drop_lowest_homework": course["drop_lowest_homework"],
        "drop_lowest_quiz": course["drop_lowest_quiz"],
        "drop_lowest_exam": course["drop_lowest_exam"],
    }
    return render_template("courses/edit.html", course=course, values=values)


@bp.route("/courses/<int:course_id>/students", methods=("POST",))
@login_required
def add_student(course_id):
    course = models.get_course(course_id)
    _require_course_edit(course)
    try:
        models.create_student(
            course_id,
            request.form.get("student_id"),
            request.form.get("name"),
            request.form.get("email"),
            request.form.get("phone"),
        )
        flash("Student added.")
    except ValueError as e:
        flash(str(e))
    return redirect(url_for("web.course_detail", course_id=course_id))


@bp.route("/courses/<int:course_id>/import-roster", methods=("POST",))
@login_required
def import_roster(course_id):
    course = models.get_course(course_id)
    _require_course_edit(course)
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Choose a CSV file to import.")
        return redirect(url_for("web.course_detail", course_id=course_id))
    result = importer.import_roster(course_id, file)
    flash(f"Roster import: {result['added']} added, "
          f"{result['skipped']} already enrolled, {len(result['errors'])} error(s).")
    for message in result["errors"][:10]:
        flash(message)
    return redirect(url_for("web.course_detail", course_id=course_id))


@bp.route("/courses/<int:course_id>/students/<int:student_id>/edit",
          methods=("GET", "POST"))
@login_required
def edit_student(course_id, student_id):
    course = models.get_course(course_id)
    _require_course_edit(course)
    student = models.get_student(student_id)
    if student is None or not models.is_enrolled(course_id, student_id):
        abort(404)
    if request.method == "POST":
        try:
            models.update_student(
                student_id,
                request.form.get("student_id"),
                request.form.get("name"),
                request.form.get("email"),
                request.form.get("phone"),
            )
            flash("Student updated.")
            return redirect(url_for("web.course_detail", course_id=course_id))
        except ValueError as e:
            flash(str(e))
            return render_template(
                "courses/edit_student.html",
                course=course, student=student, values=request.form,
            )
    values = {
        "student_id": student["student_id"],
        "name": student["name"],
        "email": student["email"] or "",
        "phone": student["phone"] or "",
    }
    return render_template(
        "courses/edit_student.html", course=course, student=student, values=values
    )


@bp.route("/courses/<int:course_id>/students/<int:student_id>/remove",
          methods=("POST",))
@login_required
def remove_student(course_id, student_id):
    course = models.get_course(course_id)
    _require_course_edit(course)
    if not models.is_enrolled(course_id, student_id):
        abort(404)
    models.unenroll(course_id, student_id)
    flash("Student removed from this course.")
    return redirect(url_for("web.course_detail", course_id=course_id))


@bp.route("/courses/<int:course_id>/students/<int:student_id>/report")
@login_required
def student_report(course_id, student_id):
    course = models.get_course(course_id)
    _require_course_edit(course)
    report = models.student_report(course_id, student_id)
    if report is None:
        abort(404)
    return render_template("courses/report.html", report=report, course=course)


@bp.route("/courses/<int:course_id>/students/<int:student_id>/report.pdf")
@download_login_required
def export_student_report_pdf(course_id, student_id):
    course = models.get_course(course_id)
    _require_course_edit(course)
    if not models.is_enrolled(course_id, student_id):
        abort(404)
    data = pdf.student_report_pdf(course_id, student_id)
    student = models.get_student(student_id)
    return _pdf_response(
        data, _pdf_filename(course["name"], student["student_id"], "report")
    )


@bp.route("/courses/<int:course_id>/assignments", methods=("POST",))
@login_required
def add_assignment(course_id):
    course = models.get_course(course_id)
    _require_course_edit(course)
    try:
        models.create_assignment(
            course_id,
            request.form.get("category"),
            request.form.get("name"),
            request.form.get("max_points"),
            bool(request.form.get("extra_credit")),
        )
        flash("Assignment added.")
    except ValueError as e:
        flash(str(e))
    return redirect(url_for("web.course_detail", course_id=course_id))


@bp.route("/assignments/<int:assignment_id>/delete", methods=("POST",))
@login_required
def delete_assignment(assignment_id):
    assignment = models.get_assignment(assignment_id)
    if assignment is None:
        abort(404)
    course = models.get_course(assignment["course_id"])
    _require_course_edit(course)
    models.delete_assignment(assignment_id)
    flash("Assignment removed.")
    return redirect(url_for("web.course_detail", course_id=course["id"]))


@bp.route("/assignments/<int:assignment_id>/edit", methods=("GET", "POST"))
@login_required
def edit_assignment(assignment_id):
    assignment = models.get_assignment(assignment_id)
    if assignment is None:
        abort(404)
    course = models.get_course(assignment["course_id"])
    _require_course_edit(course)
    if request.method == "POST":
        try:
            models.update_assignment(
                assignment_id,
                request.form.get("category"),
                request.form.get("name"),
                request.form.get("max_points"),
                bool(request.form.get("extra_credit")),
            )
            flash("Assignment updated.")
            return redirect(url_for("web.course_detail", course_id=course["id"]))
        except ValueError as e:
            flash(str(e))
            return render_template(
                "courses/edit_assignment.html",
                course=course, assignment=assignment, values=request.form,
                categories=CATEGORIES, category_labels=CATEGORY_LABELS,
            )
    values = {
        "category": assignment["category"],
        "name": assignment["name"],
        "max_points": "{:g}".format(assignment["max_points"]),
        "extra_credit": assignment["extra_credit"],
    }
    return render_template(
        "courses/edit_assignment.html",
        course=course, assignment=assignment, values=values,
        categories=CATEGORIES, category_labels=CATEGORY_LABELS,
    )


@bp.route("/assignments/<int:assignment_id>/grades", methods=("GET", "POST"))
@login_required
def grade_assignment(assignment_id):
    assignment = models.get_assignment(assignment_id)
    if assignment is None:
        abort(404)
    course = models.get_course(assignment["course_id"])
    _require_course_edit(course)
    students = models.list_students(course["id"])
    if request.method == "POST":
        errors = []
        changed = 0
        for student in students:
            raw = (request.form.get(f"points_{student['id']}") or "").strip()
            existing = models.get_grade(assignment_id, student["id"])
            if raw == "":
                if existing is not None:
                    snapshot = models.grade_snapshot(existing["id"])
                    models.clear_grade(assignment_id, student["id"])
                    notify_grade_event("removed", snapshot)
                    changed += 1
                continue
            if existing is not None and f"{existing['points']:g}" == raw:
                continue  # unchanged
            try:
                grade_id = models.set_grade(assignment_id, student["id"], raw)
            except ValueError as e:
                errors.append(f"{student['name']}: {e}")
                continue
            event = "updated" if existing is not None else "posted"
            notify_grade_event(event, models.grade_snapshot(grade_id))
            changed += 1
        if errors:
            for msg in errors:
                flash(msg)
        else:
            flash(f"Saved grades for {assignment['name']} ({changed} updated).")
            return redirect(url_for("web.course_detail", course_id=course["id"]))
    grades = {
        s["id"]: (models.get_grade(assignment_id, s["id"]) or {}) for s in students
    }
    current = {
        sid: (f"{row['points']:g}" if row else "") for sid, row in grades.items()
    }
    return render_template(
        "courses/grade_assignment.html",
        course=course,
        assignment=assignment,
        students=students,
        current=current,
    )


@bp.route("/assignments/<int:assignment_id>/import-grades", methods=("POST",))
@login_required
def import_grades(assignment_id):
    assignment = models.get_assignment(assignment_id)
    if assignment is None:
        abort(404)
    course = models.get_course(assignment["course_id"])
    _require_course_edit(course)
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Choose a CSV file to import.")
        return redirect(url_for("web.grade_assignment", assignment_id=assignment_id))
    result = importer.import_grades(assignment_id, file)
    flash(f"Grade import: {result['updated']} set, "
          f"{result['cleared']} cleared, {len(result['errors'])} error(s).")
    for message in result["errors"][:10]:
        flash(message)
    return redirect(url_for("web.grade_assignment", assignment_id=assignment_id))


@bp.route("/assignments/<int:assignment_id>/results.pdf")
@download_login_required
def export_assignment_pdf(assignment_id):
    assignment = models.get_assignment(assignment_id)
    if assignment is None:
        abort(404)
    course = models.get_course(assignment["course_id"])
    _require_course_edit(course)
    data = pdf.assignment_results_pdf(assignment_id)
    return _pdf_response(
        data, _pdf_filename(course["name"], assignment["name"], "results")
    )


@bp.route("/courses/<int:course_id>/gradebook.pdf")
@download_login_required
def export_gradebook_pdf(course_id):
    course = models.get_course(course_id)
    _require_course_edit(course)
    data = pdf.gradebook_pdf(course_id)
    return _pdf_response(data, _pdf_filename(course["name"], "gradebook"))


@bp.route("/account", methods=("GET", "POST"))
@login_required
def account():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "profile":
            try:
                models.update_contact(
                    g.user["id"], request.form.get("email"), request.form.get("phone")
                )
                flash("Contact details updated.")
                return redirect(url_for("web.account"))
            except ValueError as e:
                flash(str(e))
        if action == "password":
            current = request.form.get("current_password") or ""
            new = request.form.get("new_password") or ""
            confirm = request.form.get("confirm_password") or ""
            if not check_password_hash(g.user["password_hash"], current):
                flash("Current password is incorrect.")
            elif not new:
                flash("New password is required.")
            elif new != confirm:
                flash("New passwords do not match.")
            else:
                models.set_password(g.user["id"], new)
                flash("Password changed.")
                return redirect(url_for("web.account"))
    return render_template("account.html")
