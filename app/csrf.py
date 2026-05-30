"""Minimal CSRF protection for the server-rendered forms.

A random token is stored in the session and echoed in a hidden field on every
state-changing form (templates call ``{{ csrf_input() }}``). A ``before_request``
hook rejects any unsafe-method request whose submitted token doesn't match.

The JSON API under ``/api`` is exempt: it authenticates each request with the
session cookie *or* HTTP Basic and is meant for programmatic clients, so it
doesn't rely on ambient form credentials. Set ``CSRF_ENABLED=False`` (the test
config does) to bypass the check.
"""

import secrets

from flask import abort, request, session
from markupsafe import Markup

_FIELD = "csrf_token"
_SESSION_KEY = "_csrf_token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def generate_csrf():
    """Return the session's CSRF token, creating one on first use."""
    token = session.get(_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_SESSION_KEY] = token
    return token


def csrf_input():
    """A ready-to-drop hidden form field carrying the token."""
    return Markup(
        f'<input type="hidden" name="{_FIELD}" value="{generate_csrf()}">'
    )


def _is_valid(submitted):
    expected = session.get(_SESSION_KEY)
    return bool(expected) and bool(submitted) and secrets.compare_digest(expected, submitted)


def init_csrf(app):
    @app.context_processor
    def _inject():
        return {"csrf_token": generate_csrf, "csrf_input": csrf_input}

    @app.before_request
    def _protect():
        if not app.config.get("CSRF_ENABLED", True):
            return
        if request.method in _SAFE_METHODS:
            return
        if request.blueprint == "api":  # programmatic; cookie or HTTP Basic auth
            return
        submitted = request.form.get(_FIELD) or request.headers.get("X-CSRFToken")
        if not _is_valid(submitted):
            abort(400, description="invalid or missing CSRF token")
