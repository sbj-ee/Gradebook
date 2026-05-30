import os

from flask import Flask, redirect, url_for


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me"),
        DATABASE=os.path.join(app.instance_path, "gradebook.sqlite"),
        # CSRF protection for the server-rendered forms (the JSON API is exempt).
        CSRF_ENABLED=True,
        # Session cookie hardening. Secure is opt-in via env so local HTTP works;
        # enable it in production (HTTPS). HttpOnly + SameSite are on by default.
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").lower()
        in ("1", "true", "yes", "on"),
        # Email (SMTP) notification settings — optional; logged when unset.
        MAIL_SERVER=os.environ.get("MAIL_SERVER"),
        MAIL_PORT=int(os.environ.get("MAIL_PORT", "587")),
        MAIL_USERNAME=os.environ.get("MAIL_USERNAME"),
        MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD"),
        MAIL_FROM=os.environ.get("MAIL_FROM"),
        MAIL_USE_TLS=os.environ.get("MAIL_USE_TLS", "true").lower()
        in ("1", "true", "yes", "on"),
        # SMS (Twilio) notification settings — optional; logged when unset.
        TWILIO_ACCOUNT_SID=os.environ.get("TWILIO_ACCOUNT_SID"),
        TWILIO_AUTH_TOKEN=os.environ.get("TWILIO_AUTH_TOKEN"),
        TWILIO_FROM=os.environ.get("TWILIO_FROM"),
    )

    if test_config is not None:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    from . import admin, api, auth, csrf, db, web

    db.init_app(app)
    csrf.init_csrf(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(web.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(admin.bp)

    @app.route("/")
    def index():
        return redirect(url_for("web.list_courses"))

    # Create tables on first run so the app is usable without a manual step.
    with app.app_context():
        db.init_db_if_needed()

    return app
