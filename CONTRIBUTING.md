# Contributing

Thanks for your interest in improving Gradebook! This is a small Flask + SQLite project, so
the workflow is intentionally lightweight.

## Getting set up

1. Fork and clone the repo, then create a branch off `main`:

   ```bash
   git checkout -b my-change
   ```

2. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```

   > If `python3 -m venv` fails with *"ensurepip is not available"* (common on
   > Debian/Ubuntu without the `python3-venv` package), bootstrap pip manually:
   >
   > ```bash
   > python3 -m venv .venv --without-pip
   > source .venv/bin/activate
   > curl -sS https://bootstrap.pypa.io/get-pip.py | python
   > pip install -r requirements-dev.txt
   > ```

## Running the app

The SQLite database is created automatically on first run at
`instance/gradebook.sqlite`. Use Flask's reloader during development:

```bash
flask --app app run --debug
```

To run it the way it's deployed, use gunicorn:

```bash
SECRET_KEY=dev gunicorn -w 4 -b 127.0.0.1:8000 wsgi:app
```

Reset the database at any time with `flask --app app init-db`. Create an admin user with
`flask --app app create-admin <username> <password>` (or `set-admin <username>` to promote
an existing one) to access the `/admin` control panel.

## Tests

Every change should keep the suite green, and new behavior should come with tests.

```bash
pytest
```

Tests live in `tests/` and use a throwaway temporary database per test (see
`tests/conftest.py`), so they never touch your `instance/` data.

## Project layout

| Path | Purpose |
| --- | --- |
| `app/__init__.py` | App factory; auto-creates the DB on first run |
| `app/db.py` | SQLite connection + `init-db` / `create-admin` CLI commands |
| `app/schema.sql` | `user` / `course` / `student` / `enrollment` / `assignment` / `grade` tables |
| `app/models.py` | Data access + weight validation (`WeightError`) + grade computation |
| `app/utils.py` | Pure grade math (category %, weighted final, letter grade) |
| `app/auth.py` | Register/login/logout + `login_required` / `admin_required` / `api_auth_required` |
| `app/web.py` | Server-rendered UI routes |
| `app/api.py` | JSON API routes under `/api` |
| `app/admin.py` | Admin panel routes under `/admin`, CSV export, notifications log |
| `app/pdf.py` | PDF exports (assignment results, full gradebook) via fpdf2 — IDs only |
| `app/notifications.py` | Email (SMTP) + SMS (Twilio) channels with log/audit fallback |
| `app/templates/`, `app/static/` | Jinja templates and CSS |
| `tests/` | pytest suite |
| `wsgi.py` | gunicorn entrypoint (`wsgi:app`) |

A few conventions worth knowing:

- **Shared data logic lives in `app/models.py`.** Both the web and API layers call the
  same functions, so business rules (weight validation, grade bounds, the weighted-average
  computation) stay in one place. Add new query/mutation logic there rather than inside
  route handlers.
- **Grade math is pure and lives in `app/utils.py`.** `category_percentage`,
  `weighted_final`, and `letter_grade` take plain numbers and dicts — no database, no
  Flask — so they're easy to unit-test. Reuse them rather than recomputing in a route.
- **Course weights must total 100.** `models.create_course` / `update_course` coerce and
  validate the three weights and raise `WeightError` otherwise; routes catch it and flash
  / return the message. A category with no graded work is dropped and the rest renormalized.
- **`student_id` is the visible identifier.** It's the school-assigned student ID shown
  throughout the UI and is **globally unique**; the integer primary key (`student.id`) is
  only used internally and in foreign keys.
- **Students are global; `enrollment` joins them to courses.** A `student` row is one
  person (independent of any course); an `enrollment` row links a student to a course. The
  same student can be enrolled in many courses. `create_student` reuses an existing student
  when the visible ID already exists; "removing" a student from a course un-enrolls them
  (and drops that course's grades) but keeps the shared student record. Per-student grade
  queries are therefore course-scoped (`student_grade(course_id, student_id)`).
- **API errors** return JSON `{"error": "..."}` with a meaningful status code
  (`400` bad input, `401` unauthenticated, `403` forbidden, `404` missing).
- **Course ownership:** a course is editable by an admin or the teacher who created it
  (`course.created_by`). Roster/assignment/grade changes enforce this in both the web and
  API layers.
- **User uniqueness:** username, email, and phone are unique (emails/phones are optional, so
  NULLs are allowed and don't collide). Insert/update through `app/models.py`, which converts
  a SQLite `UNIQUE` violation into a friendly, field-specific `ValueError` via
  `unique_violation_message`; routes catch it and flash the message.
- **PDF exports never print student names.** `app/pdf.py` (assignment results + full
  gradebook, built with fpdf2) identifies students by their `student_id` only; keep it that
  way. Output is left uncompressed on purpose so tests can assert no name leaks into the
  bytes. Text uses the core Helvetica font, so stick to ASCII/Latin-1 punctuation.
- **Notifications** fire from the route layer after a grade is posted/changed/removed via
  `app/notifications.py`. Email/SMS providers are configured with env vars (`MAIL_*`,
  `TWILIO_*`); when unset, messages are logged and recorded to the `notification` table, so
  tests and local dev work without credentials. Dispatch must never raise into the request.

## Style

- Standard PEP 8 / 4-space indentation. Keep imports tidy and functions small.
- Match the surrounding code; avoid introducing new dependencies without discussion.

## Submitting changes

1. Make sure `pytest` passes.
2. Use clear, focused commits with descriptive messages.
3. Open a pull request against `main` describing **what** changed and **why**, and
   mention any new endpoints or schema changes.

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
