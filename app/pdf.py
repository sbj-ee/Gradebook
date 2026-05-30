"""PDF exports: a single assignment's results, and a whole-course gradebook.

By design these never print student names — only the visible student ID — so the
output can be posted or shared without exposing who earned what.

Built with fpdf2. Output is left uncompressed: the documents are small (a class
roster), and it keeps the text inspectable, which the tests rely on to assert that
no student name leaks into the file.

Text is restricted to Latin-1 (the core Helvetica font's encoding); helpers below
stick to ASCII punctuation so an unusual character can't raise at render time.
"""

from datetime import datetime, timezone

from fpdf import FPDF

from . import models
from .utils import CATEGORIES, CATEGORY_LABELS, category_percentage

PRIVACY_NOTE = "Student names omitted; identified by student ID only."


def _num(n):
    """Trim a float for display: 18.0 -> '18', 18.5 -> '18.5'."""
    return f"{n:g}"


def _pct(value):
    return f"{value:g}%" if value is not None else "-"


def _timestamp():
    return "Generated " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _new_pdf(orientation, title):
    pdf = FPDF(orientation=orientation, unit="mm", format="A4")
    pdf.set_compression(False)
    pdf.set_auto_page_break(True, margin=15)
    pdf.set_title(title)
    pdf.add_page()
    return pdf


def _meta_line(pdf, text):
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(120)
    pdf.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)


def assignment_results_pdf(assignment_id):
    """Bytes of a PDF listing each student's score on one assignment. Returns None
    if the assignment doesn't exist."""
    assignment = models.get_assignment(assignment_id)
    if assignment is None:
        return None
    course = models.get_course(assignment["course_id"])
    students = models.list_students(course["id"])
    max_points = assignment["max_points"]

    pdf = _new_pdf("P", f"{course['name']} - {assignment['name']}")
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, course["name"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    subtitle = f"{CATEGORY_LABELS[assignment['category']]} - {assignment['name']}"
    if assignment["extra_credit"]:
        subtitle += " (extra credit)"
    pdf.cell(0, 7, subtitle, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"Out of {_num(max_points)} points", new_x="LMARGIN", new_y="NEXT")
    _meta_line(pdf, _timestamp() + ". " + PRIVACY_NOTE)
    pdf.ln(3)

    rows = [("Student ID", "Points", "Percent")]
    scored = []
    for s in students:
        grade = models.get_grade(assignment_id, s["id"])
        if grade is None:
            rows.append((s["student_id"], "-", "-"))
        else:
            scored.append(grade["points"])
            rows.append(
                (s["student_id"], _num(grade["points"]),
                 _pct(category_percentage(grade["points"], max_points)))
            )

    pdf.set_font("Helvetica", "", 10)
    with pdf.table(
        col_widths=(45, 25, 25),
        text_align=("LEFT", "RIGHT", "RIGHT"),
        first_row_as_headings=True,
    ) as table:
        for r in rows:
            tr = table.row()
            for cell in r:
                tr.cell(str(cell))

    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    if scored:
        avg = round(sum(scored) / len(scored), 2)
        avg_pct = category_percentage(sum(scored), max_points * len(scored))
        summary = (f"Graded: {len(scored)} of {len(students)}    "
                   f"Average: {_num(avg)} / {_num(max_points)} ({_pct(avg_pct)})")
    else:
        summary = f"Graded: 0 of {len(students)}"
    pdf.cell(0, 6, summary, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def student_report_pdf(course_id, student_id):
    """Bytes of a one-student report card (ID only). Returns None if not enrolled."""
    report = models.student_report(course_id, student_id)
    if report is None:
        return None
    course = report["course"]

    pdf = _new_pdf("P", f"{course['name']} - report card")
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, course["name"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"Report card - Student {report['student']['student_id']}",
             new_x="LMARGIN", new_y="NEXT")
    _meta_line(pdf, _timestamp() + ". " + PRIVACY_NOTE)
    pdf.ln(2)

    for cat in report["categories"]:
        pdf.set_font("Helvetica", "B", 12)
        heading = f"{cat['label']}  (weight {cat['weight']}%"
        heading += f", drop {cat['drop']} lowest)" if cat["drop"] else ")"
        pdf.cell(0, 8, heading, new_x="LMARGIN", new_y="NEXT")
        rows = [("Assignment", "Score", "Percent")]
        for a in cat["assignments"]:
            name = a["name"] + (" (EC)" if a["extra_credit"] else "")
            if a["dropped"]:
                name += " (dropped)"
            if a["points"] is None:
                rows.append((name, "-", "-"))
            else:
                rows.append((name, f"{_num(a['points'])} / {_num(a['max_points'])}",
                             _pct(a["pct"])))
        pdf.set_font("Helvetica", "", 10)
        with pdf.table(col_widths=(60, 25, 20),
                       text_align=("LEFT", "RIGHT", "RIGHT"),
                       first_row_as_headings=True) as table:
            for r in rows:
                tr = table.row()
                for cell in r:
                    tr.cell(str(cell))
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 7, f"  {cat['label']} total: {_pct(cat['pct'])}",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    pdf.set_font("Helvetica", "B", 13)
    final = _pct(report["final"]) if report["final"] is not None else "-"
    letter = report["letter"] if report["final"] is not None else "-"
    pdf.cell(0, 9, f"Final: {final}   Grade: {letter}", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def gradebook_pdf(course_id):
    """Bytes of a PDF of the full gradebook grid (IDs only). Returns None if the
    course doesn't exist."""
    book = models.course_gradebook(course_id)
    if book is None:
        return None
    course = book["course"]
    assignments = book["assignments"]
    weights = book["weights"]

    pdf = _new_pdf("L", f"{course['name']} gradebook")
    pdf.set_font("Helvetica", "B", 16)
    title = course["name"] + (f" - {course['term']}" if course["term"] else "")
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
    _meta_line(
        pdf,
        f"Weighting: Homework {weights['homework']}% / Quizzes {weights['quiz']}%"
        f" / Exams {weights['exam']}%",
    )
    _meta_line(pdf, _timestamp() + ". " + PRIVACY_NOTE)
    pdf.ln(2)

    header = ["Student ID"]
    for a in assignments:
        header.append(a["name"] + (" (EC)" if a["extra_credit"] else ""))
    header += ["HW %", "Quiz %", "Exam %", "Final %", "Grade"]

    data = [header]
    for r in book["rows"]:
        line = [r["student"]["student_id"]]
        for a in assignments:
            points = r["grades"].get(a["id"])
            line.append(_num(points) if points is not None else "-")
        for cat in CATEGORIES:
            pct = r["categories"][cat]["pct"]
            line.append(_num(pct) if pct is not None else "-")
        line.append(_num(r["final"]) if r["final"] is not None else "-")
        line.append(r["letter"] if r["final"] is not None else "-")
        data.append(line)

    pdf.set_font("Helvetica", "", 8)
    with pdf.table(first_row_as_headings=True, text_align="CENTER") as table:
        for row in data:
            tr = table.row()
            for cell in row:
                tr.cell(str(cell))
    return bytes(pdf.output())
