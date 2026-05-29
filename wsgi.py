from app import create_app

# WSGI entrypoint used by gunicorn:  gunicorn wsgi:app
app = create_app()
