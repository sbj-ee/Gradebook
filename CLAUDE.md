# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A **Flask + SQLite** gradebook web app (served with **gunicorn**). Teachers register/log in,
create courses, enroll students, add assignments in weighted categories (homework/quizzes/
exams), and the app computes weighted finals + letter grades. Ships a server-rendered web UI
**and** a JSON API.

## Layout (`app/` package)

- `__init__.py` — Flask **app factory**.
- `web.py` — server-rendered routes; `api.py` — JSON API routes.
- `auth.py` — accounts/login (password hashing via **Werkzeug**); `csrf.py` — CSRF protection.
- `admin.py` — admin views; `models.py` — data access; `db.py` — connection/helpers.
- `schema.sql` — **SQLite schema** (source of truth for tables).
- `importer.py` (bulk import), `pdf.py` (report PDFs via **fpdf2**), `notifications.py`,
  `utils.py`.
- `templates/` (Jinja, organized by area), `static/` (css/svg/js).

## Setup, run & test

- Python **3.12**. `pip install -r requirements.txt` (dev: `requirements-dev.txt`).
- Run via the app factory — gunicorn in prod (see `Procfile`), Flask dev server locally.
  Initialize the DB from `app/schema.sql`.
- **Tests:** `pytest` (config in `pytest.ini`). **Lint:** `ruff`.
- **Docker:** `Dockerfile` + `.dockerignore` provided. **CI:** `.github/workflows/ci.yml`.

## Conventions

- Keep **web vs API** concerns split (`web.py` vs `api.py`); share logic via `models.py`/
  `utils.py`, don't duplicate.
- Auth/session + CSRF are centralized (`auth.py`, `csrf.py`) — route new mutating endpoints
  through them; never roll your own password handling.
- Schema changes go in `app/schema.sql` and the models together.
- Grade math (category weights, extra-credit, drop-lowest) is core logic — add tests when you
  touch it.

## Public repo

This repository is **public**. Do not add secrets, real user data, or anything sensitive to
code, tests, fixtures, or commits. Use `SECRET_KEY`/DB paths from env/config, never hardcoded.
