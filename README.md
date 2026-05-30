# Gradebook

![Python](https://img.shields.io/badge/python-3.12-3776AB.svg?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000.svg?logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57.svg?logo=sqlite&logoColor=white)
![Gunicorn](https://img.shields.io/badge/server-gunicorn-499848.svg?logo=gunicorn&logoColor=white)
![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC.svg?logo=pytest&logoColor=white)
[![CI](https://github.com/sbj-ee/Gradebook/actions/workflows/ci.yml/badge.svg)](https://github.com/sbj-ee/Gradebook/actions/workflows/ci.yml)

A small gradebook built with **Python, Flask, and SQLite**. Teachers register and log
in, create **courses** (classes), enroll any number of **students**, add **assignments**
in three categories — homework, quizzes, and exams — and enter grades. Each course gives
the categories a configurable weight, and the app computes every student's weighted final
percentage and letter grade. It ships with both a server-rendered web UI and a JSON API,
and is served with **gunicorn**.

## Features

- Username/password accounts (session login + password hashing via Werkzeug)
- Unique usernames, emails, and phone numbers (email/phone optional)
- Self-service "forgot password": a single-use, time-limited reset link sent by email
- Courses: anyone can browse; logged-in users create and manage their own
- **Configurable weighting** per course for homework, quizzes, and exams (must total 100)
- Variable-size rosters: enroll any number of students, each with a visible **student ID**;
  a student is a shared record (editable anytime) and can be enrolled in multiple courses
- Assignments with a category and max points; grades are bounded to `0..max`
- **Automatic grade computation**: per-category percentages, a weighted final, and a
  letter grade — a category with no graded work is dropped and the rest renormalized
- Web UI (Jinja templates) **and** a JSON API under `/api`
- API accepts either the session cookie or HTTP Basic auth
- Admin control panel at `/admin` to manage users and courses
- Self-service account page (`/account`): update your email/phone and change your password
- Last-login tracking: shown as a "welcome back" banner on sign-in and in the admin user list
- CSV **import** of a roster (`student_id, name, email, phone`) and of per-assignment
  grades (`student_id, points`), and CSV **export** of grades (filterable by course / category)
- PDF export of a single assignment's results, or the whole gradebook — **student IDs
  only, no names**, so results can be posted or shared
- Email + SMS notifications to students when a grade is posted, changed, or removed
- CSRF-protected forms, hardened session cookie, and downloads that 401 (not redirect)
  when unauthenticated

## Setup

Python 3.12. Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The SQLite database is created automatically on first run at
`instance/gradebook.sqlite`. To reset it explicitly:

```bash
flask --app app init-db
```

## Run

Production-style, with gunicorn (the WSGI entrypoint is `wsgi:app`):

```bash
SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  gunicorn -w 4 -b 127.0.0.1:8000 wsgi:app
```

Then open http://127.0.0.1:8000/.

For local development with auto-reload you can instead use Flask's server:

```bash
flask --app app run --debug
```

Or with Docker (a `Dockerfile` and `Procfile` are included):

```bash
docker build -t gradebook .
docker run -p 8000:8000 -e SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" gradebook
```

## How grading works

Each course assigns a whole-percentage **weight** to homework, quizzes, and exams; the
three weights must add up to 100. For a given student:

1. A **category percentage** is the points they earned divided by the points possible
   across the assignments they were graded on, in that category. Assignments a student
   hasn't been graded on don't count against them.
2. Optionally, the **lowest N scores are dropped** from each category before averaging
   (configured per course). Extra-credit assignments are never dropped.
3. The **final percentage** is the weighted average of the categories that have at least
   one grade. Empty categories are excluded and the surviving weights are renormalized, so
   a student isn't penalized for work that hasn't been assigned or graded yet.
4. The **letter grade** uses the course's chosen scale: **standard** (90/80/70/60 →
   A/B/C/D, else F) or **plus/minus** (A+, A, A-, B+, … with the usual cutoffs).

For example, with weights 40/20/40 and scores of 90% homework, 80% quizzes, 70% exams:
`(90·40 + 80·20 + 70·40) / 100 = 80.0` → **B**. If only homework has been graded, the
final is simply the homework percentage. This logic lives in `app/utils.py` (pure
functions) and is exercised directly in `tests/test_utils.py`.

## Admin

Admins get a control panel at `/admin` to manage **users** (edit username/email/phone,
reset password, grant/revoke admin, delete) and **courses** (open, delete). The panel and
its nav link are visible only to admin users. Every signed-in user can manage their own
email, phone, and password from the **Account** page (`/account`), and can fully manage the
courses they created (roster, assignments, grades) from each course page.

Locked out? **Forgot password?** on the login page (`/auth/forgot`) emails a single-use
reset link that expires in an hour. Tokens are stored only as a SHA-256 hash, so a database
leak can't produce a working link. As with all notifications, when email isn't configured
the link is written to the app log and recorded (rather than delivered) — see
[Notifications](#notifications).

Create the first admin from the command line, then log in normally:

```bash
flask --app app create-admin alice s3cret      # new admin user
flask --app app set-admin bob                   # grant admin to an existing user
flask --app app set-admin bob --remove          # revoke it
```

## Reports

Admins can export grades as CSV:

- **Filtered:** **Admin → Courses** has a filter form (course + category) whose
  **Export grades CSV** button downloads the matching rows.
- **Directly:**

```
GET /admin/reports/grades.csv?course_id=1&category=exam
```

Both query parameters are optional. The file has one row per grade with the course,
student ID, student name, category, assignment, extra-credit flag, points, max points, and
creation timestamp.

The CSV is UTF-8 and begins with a byte-order mark (BOM), which lets LibreOffice Calc and
Excel detect the encoding automatically when the file is opened directly. The first row is
the header. If a spreadsheet app drops the header on import, check its text-import dialog —
in LibreOffice's *Text Import* dialog make sure **From row** is `1` (it remembers the last
value used) and the **Separator** is **Comma**.

### CSV import

To populate a course quickly, the course page has an **Import roster CSV** form
(`student_id, name, email, phone` — headers are matched case-insensitively and a UTF-8 BOM
is tolerated), and each assignment's grade-entry page has an **Import grades CSV** form
(`student_id, points`; a blank `points` clears that grade). Both report how many rows were
applied, skipped, or failed, and a bad row never aborts the rest of the file.

### PDF exports

For sharing or posting results, two PDF exports are available to the course owner (or an
admin). **Neither prints student names — students are identified by their student ID only.**

- **Assignment results:** the **PDF** link on each assignment (course page or grade-entry
  page) downloads that assignment's scores with each student's points, percent, and a
  class average.

  ```
  GET /assignments/<id>/results.pdf
  ```

- **Whole gradebook:** the **Export gradebook PDF** button on the course page downloads the
  full grid (every assignment, per-category percentages, weighted final, and letter grade)
  in landscape.

  ```
  GET /courses/<id>/gradebook.pdf
  ```

- **Per-student report card:** the **Report** link on each student opens a full breakdown
  (every assignment by category, dropped scores marked, category subtotals, and the final
  grade), with an **Export PDF** button.

  ```
  GET /courses/<id>/students/<id>/report.pdf
  ```

## Notifications

When a grade is **posted, changed, or removed**, the affected student is notified on every
channel they have contact info for (email and/or SMS — captured optionally when enrolling).

The mechanism is pluggable and configured entirely through environment variables. When a
channel isn't configured, the message is written to the application log and an audit row is
still recorded, so the feature works out of the box without any credentials. Every attempt
(`sent` / `failed` / `logged` / `skipped`) is visible to admins at **Admin → Notifications**.
A failed send never blocks the grade from being saved.

| Variable | Channel | Notes |
| --- | --- | --- |
| `MAIL_SERVER`, `MAIL_FROM` | Email | Required to enable email (SMTP) |
| `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_USE_TLS` | Email | Optional (port defaults to 587, TLS on) |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` | SMS | All three required to enable SMS (Twilio) |

```bash
# example: enable real email delivery
MAIL_SERVER=smtp.example.com MAIL_FROM=grades@example.com \
MAIL_USERNAME=apikey MAIL_PASSWORD=secret \
  gunicorn -w 4 -b 127.0.0.1:8000 wsgi:app
```

## API

`POST` endpoints require authentication (session cookie or HTTP Basic). Writes to a course
(students, assignments, grades) additionally require that you created the course or are an
admin. `GET` endpoints are public.

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/api/courses` | no | List courses |
| POST | `/api/courses` | yes | Create a course (`{name, term, description, weights}`) |
| GET | `/api/courses/<id>` | no | Course detail + its students and assignments |
| GET | `/api/courses/<id>/gradebook` | no | Computed gradebook (every student's totals) |
| GET | `/api/courses/<id>/students` | no | List a course's students |
| POST | `/api/courses/<id>/students` | owner | Enroll a student (`{student_id, name, email, phone}`); reuses an existing student ID |
| PUT | `/api/students/<id>` | owner | Edit a student's shared record (`{student_id, name, email, phone}`) |
| GET | `/api/courses/<id>/assignments` | no | List a course's assignments |
| POST | `/api/courses/<id>/assignments` | owner | Add an assignment (`{category, name, max_points}`) |
| POST | `/api/assignments/<id>/grades` | owner | Set a grade (`{student_id, points}`) — `400` if out of range |
| GET | `/api/courses/<id>/students/<id>/grade` | no | A student's computed grade summary in that course |

`weights` is `{"homework": h, "quiz": q, "exam": e}` (whole percentages summing to 100);
omit it to use the 40/20/40 default. `category` is one of `homework`, `quiz`, `exam`.
Errors return JSON `{"error": "..."}` with a meaningful status code (`400` bad input,
`401` unauthenticated, `403` forbidden, `404` missing).

### Example

```bash
# create a course with HTTP Basic auth
curl -u alice:secret -X POST http://127.0.0.1:8000/api/courses \
  -H 'Content-Type: application/json' \
  -d '{"name": "Algebra I", "term": "Fall 2026", "weights": {"homework": 40, "quiz": 20, "exam": 40}}'

# enroll a student, add an exam, and record a grade
curl -u alice:secret -X POST http://127.0.0.1:8000/api/courses/1/students \
  -H 'Content-Type: application/json' -d '{"student_id": "S1001", "name": "Jordan Lee"}'
curl -u alice:secret -X POST http://127.0.0.1:8000/api/courses/1/assignments \
  -H 'Content-Type: application/json' -d '{"category": "exam", "name": "Midterm", "max_points": 100}'
curl -u alice:secret -X POST http://127.0.0.1:8000/api/assignments/1/grades \
  -H 'Content-Type: application/json' -d '{"student_id": 1, "points": 92}'
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Project layout

```
app/
  __init__.py      app factory; auto-creates the DB on first run
  db.py            SQLite connection + init-db / create-admin CLI commands
  schema.sql       user / course / student / enrollment / assignment / grade tables
  models.py        data access + weight validation + grade computation
  utils.py         pure grade math (category %, weighted final, letter grade)
  auth.py          register/login/logout + login_required / admin_required / api_auth_required
  web.py           server-rendered UI routes
  api.py           JSON API routes (/api)
  admin.py         admin control panel routes (/admin) + CSV export + notifications log
  pdf.py           PDF exports (assignment results, full gradebook) — IDs only, no names
  importer.py      CSV import of rosters and per-assignment grades
  notifications.py email (SMTP) + SMS (Twilio) channels with log/audit fallback
  templates/       Jinja templates
  static/          style.css + tz.js (UTC→local) + favicon/logo
tests/             pytest suite
wsgi.py            gunicorn entrypoint (wsgi:app)
```

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for setup, testing,
and pull request guidelines.

## License

Released under the [MIT License](LICENSE).
