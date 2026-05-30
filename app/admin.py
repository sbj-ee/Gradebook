import csv
import io

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from . import models
from .auth import admin_required, download_admin_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@admin_required
def dashboard():
    return render_template("admin/dashboard.html", counts=models.counts())


# --- Users -----------------------------------------------------------------

@bp.route("/users")
@admin_required
def users():
    return render_template("admin/users.html", users=models.list_users())


@bp.route("/users/<int:user_id>/edit", methods=("GET", "POST"))
@admin_required
def edit_user(user_id):
    user = models.get_user(user_id)
    if user is None:
        abort(404)
    if request.method == "POST":
        try:
            models.update_user_account(
                user_id,
                request.form.get("username"),
                request.form.get("email"),
                request.form.get("phone"),
            )
            new_password = (request.form.get("new_password") or "").strip()
            if new_password:
                models.set_password(user_id, new_password)
            flash("User updated.")
            return redirect(url_for("admin.users"))
        except ValueError as e:
            flash(str(e))
            return render_template("admin/user_edit.html", user=user, values=request.form)
    values = {
        "username": user["username"],
        "email": user["email"] or "",
        "phone": user["phone"] or "",
    }
    return render_template("admin/user_edit.html", user=user, values=values)


@bp.route("/users/<int:user_id>/toggle-admin", methods=("POST",))
@admin_required
def toggle_admin(user_id):
    user = models.get_user(user_id)
    if user is None:
        abort(404)
    if user["id"] == g.user["id"]:
        flash("You cannot change your own admin status.")
    else:
        models.set_user_admin(user_id, not user["is_admin"])
        flash(f"Updated admin status for {user['username']}.")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/delete", methods=("POST",))
@admin_required
def delete_user(user_id):
    user = models.get_user(user_id)
    if user is None:
        abort(404)
    if user["id"] == g.user["id"]:
        flash("You cannot delete your own account.")
    else:
        models.delete_user(user_id)
        flash(f"Deleted user {user['username']}.")
    return redirect(url_for("admin.users"))


# --- Courses ---------------------------------------------------------------

@bp.route("/courses")
@admin_required
def courses():
    return render_template("admin/courses.html", courses=models.list_courses())


@bp.route("/courses/<int:course_id>/delete", methods=("POST",))
@admin_required
def delete_course(course_id):
    course = models.get_course(course_id)
    if course is None:
        abort(404)
    models.delete_course(course_id)
    flash(f"Deleted course {course['name']} and all its students, assignments, and grades.")
    return redirect(url_for("admin.courses"))


# --- Reports ---------------------------------------------------------------

@bp.route("/reports/grades.csv")
@download_admin_required
def grades_csv():
    rows = models.query_grades(
        course_id=request.args.get("course_id", type=int),
        category=request.args.get("category"),
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["course", "student_id", "student", "category",
         "assignment", "extra_credit", "points", "max_points", "created_at"]
    )
    for r in rows:
        writer.writerow([
            r["course_name"], r["student_id"], r["student_name"], r["category"],
            r["assignment_name"], "yes" if r["extra_credit"] else "no",
            f"{r['points']:g}", f"{r['max_points']:g}", r["created_at"],
        ])
    # Prefix a UTF-8 BOM so LibreOffice Calc / Excel detect the encoding reliably
    # when the file is opened directly. Flask adds "; charset=utf-8" for text/*.
    return Response(
        "\ufeff" + buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=grades.csv"},
    )


# --- Notifications log -----------------------------------------------------

@bp.route("/notifications")
@admin_required
def notifications():
    return render_template(
        "admin/notifications.html", notifications=models.list_notifications()
    )
