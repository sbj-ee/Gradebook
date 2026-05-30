FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so they cache across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The SQLite database lives under instance/; persist it with a volume in prod.
ENV PORT=8000
EXPOSE 8000

# Provide a real SECRET_KEY at runtime: docker run -e SECRET_KEY=...
CMD ["sh", "-c", "gunicorn -w 4 -b 0.0.0.0:${PORT} wsgi:app"]
