"""CSV import of rosters and per-assignment grades.

Both importers are tolerant: headers are matched case-insensitively (spaces become
underscores), a UTF-8 BOM is stripped, blank lines are skipped, and a bad row is
reported rather than aborting the whole file. Each returns a summary dict the route
turns into flash messages.

Roster CSV columns:  student_id, name, [email], [phone]
Grades CSV columns:  student_id, points   (blank points clears the grade)
"""

import csv
import io

from . import models
from .notifications import notify_grade_event


def _read_rows(file_storage):
    text = file_storage.read().decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for raw in reader:
        rows.append({
            (k or "").strip().lower().replace(" ", "_"): (v or "").strip()
            for k, v in raw.items()
        })
    return rows


def import_roster(course_id, file_storage):
    """Enroll each CSV row into the course. Returns {added, skipped, errors}."""
    added = skipped = 0
    errors = []
    for i, row in enumerate(_read_rows(file_storage), start=2):  # row 1 is the header
        code = row.get("student_id", "")
        name = row.get("name", "")
        if not code and not name:
            continue
        try:
            models.create_student(
                course_id, code, name, row.get("email"), row.get("phone")
            )
            added += 1
        except ValueError as e:
            if "already enrolled" in str(e):
                skipped += 1
            else:
                errors.append(f"row {i}: {e}")
    return {"added": added, "skipped": skipped, "errors": errors}


def import_grades(assignment_id, file_storage):
    """Set each CSV row's grade on the assignment (blank points clears it). Returns
    {updated, cleared, errors}."""
    assignment = models.get_assignment(assignment_id)
    updated = cleared = 0
    errors = []
    for i, row in enumerate(_read_rows(file_storage), start=2):
        code = row.get("student_id", "")
        if not code:
            continue
        student = models.get_student_by_code(code)
        if student is None or not models.is_enrolled(assignment["course_id"], student["id"]):
            errors.append(f"row {i}: student {code!r} is not enrolled in this course")
            continue
        existing = models.get_grade(assignment_id, student["id"])
        points = row.get("points", "")
        if points == "":
            if existing is not None:
                snapshot = models.grade_snapshot(existing["id"])
                models.clear_grade(assignment_id, student["id"])
                notify_grade_event("removed", snapshot)
                cleared += 1
            continue
        try:
            grade_id = models.set_grade(assignment_id, student["id"], points)
        except ValueError as e:
            errors.append(f"row {i}: {e}")
            continue
        notify_grade_event(
            "updated" if existing is not None else "posted",
            models.grade_snapshot(grade_id),
        )
        updated += 1
    return {"updated": updated, "cleared": cleared, "errors": errors}
