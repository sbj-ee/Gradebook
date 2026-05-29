"""Grade notifications.

A small pluggable mechanism: each grade event (posted / updated / removed) is
delivered to the student over any channel they have contact info for. Email uses
SMTP and SMS uses the Twilio REST API, both configured via environment variables
(see ``create_app``). When a channel isn't configured, the message is logged and an
audit row is still recorded, so the mechanism is fully exercisable without secrets.

Every attempt is written to the ``notification`` table with a status:

- ``sent``     delivered through a configured provider
- ``failed``   provider configured but raised an error (details captured)
- ``logged``   provider not configured; message written to the app log
- ``skipped``  the student has no contact info for any channel

Dispatch never raises into the request flow — a notification problem must not
prevent a grade from being saved.
"""

import base64
import smtplib
import urllib.parse
import urllib.request
from email.message import EmailMessage

from flask import current_app

from . import models

EVENT_VERB = {
    "posted": "posted",
    "updated": "updated",
    "removed": "removed",
}


def email_configured():
    c = current_app.config
    return bool(c.get("MAIL_SERVER") and c.get("MAIL_FROM"))


def sms_configured():
    c = current_app.config
    return all(
        c.get(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM")
    )


def _build_message(event, snapshot):
    verb = EVENT_VERB.get(event, event)
    subject = f"Grade {verb}: {snapshot['assignment_name']} ({snapshot['course_name']})"
    lines = [
        f"Hi {snapshot['student_name']},",
        "",
        f"A grade was {verb} for \"{snapshot['assignment_name']}\" "
        f"in {snapshot['course_name']}.",
    ]
    if event != "removed":
        lines.append(
            f"  Score: {snapshot['points']:g} / {snapshot['max_points']:g}"
        )
    lines += ["", "— Gradebook"]
    return subject, "\n".join(lines)


def _send_email(to_addr, subject, body):
    c = current_app.config
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = c["MAIL_FROM"]
    msg["To"] = to_addr
    msg.set_content(body)
    with smtplib.SMTP(c["MAIL_SERVER"], c.get("MAIL_PORT", 587), timeout=10) as smtp:
        if c.get("MAIL_USE_TLS", True):
            smtp.starttls()
        if c.get("MAIL_USERNAME"):
            smtp.login(c["MAIL_USERNAME"], c.get("MAIL_PASSWORD") or "")
        smtp.send_message(msg)


def _send_sms(to_number, body):
    c = current_app.config
    sid = c["TWILIO_ACCOUNT_SID"]
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode(
        {"From": c["TWILIO_FROM"], "To": to_number, "Body": body}
    ).encode()
    token = base64.b64encode(f"{sid}:{c['TWILIO_AUTH_TOKEN']}".encode()).decode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def _deliver(grade_id, student_id, event, channel, recipient, configured, do_send, subject, body):
    """Run one channel: send if configured, else log; record the outcome either way."""
    status, detail = "logged", ""
    if configured:
        try:
            do_send()
            status = "sent"
        except Exception as e:  # provider error must not break the caller
            status, detail = "failed", f"{type(e).__name__}: {e}"
            current_app.logger.warning(
                "%s notification to %s failed: %s", channel, recipient, detail
            )
    else:
        current_app.logger.info(
            "[notification:%s] to=%s subject=%r body=%r", channel, recipient, subject, body
        )
    models.record_notification(
        grade_id, student_id, event, channel, recipient, subject, body, status, detail
    )


def notify_grade_event(event, snapshot):
    """Notify a student of a grade event. ``snapshot`` is a grade row joined with
    assignment / course names and the student's contact info (see
    models.grade_snapshot). Never raises."""
    if snapshot is None:
        return
    try:
        subject, body = _build_message(event, snapshot)
        gid, sid = snapshot["id"], snapshot["student_id"]
        delivered = False
        if snapshot["student_email"]:
            _deliver(gid, sid, event, "email", snapshot["student_email"], email_configured(),
                     lambda: _send_email(snapshot["student_email"], subject, body), subject, body)
            delivered = True
        if snapshot["student_phone"]:
            _deliver(gid, sid, event, "sms", snapshot["student_phone"], sms_configured(),
                     lambda: _send_sms(snapshot["student_phone"], body), subject, body)
            delivered = True
        if not delivered:
            models.record_notification(
                gid, sid, event, "none", "", subject, body,
                "skipped", "student has no email or phone on file",
            )
    except Exception as e:
        current_app.logger.exception("notification dispatch failed: %s", e)


def notify_password_reset(user_id, email, username, reset_url):
    """Email a password-reset link over the email channel. Never raises."""
    try:
        subject = "Reset your Gradebook password"
        body = "\n".join([
            f"Hi {username},",
            "",
            "We received a request to reset your password. Open the link below to choose "
            "a new one:",
            reset_url,
            "",
            "This link expires in 1 hour and can be used once. If you didn't request it, "
            "you can safely ignore this email.",
            "",
            "— Gradebook",
        ])
        _deliver(None, user_id, "password_reset", "email", email, email_configured(),
                 lambda: _send_email(email, subject, body), subject, body)
    except Exception as e:
        current_app.logger.exception("password reset notification failed: %s", e)
