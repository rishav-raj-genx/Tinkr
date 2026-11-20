FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=7860

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=10001:10001 . .
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin tinkr \
    && chown -R tinkr:tinkr /app

USER tinkr

# The database is deliberately created at container start because Space and
# other free-tier filesystems are ephemeral. No OAuth token is copied into the image.
CMD ["sh", "-c", "if [ ! -f \"${DB_PATH:-/app/company_data.db}\" ]; then python setup_db.py; fi; exec gunicorn --bind 0.0.0.0:${PORT:-7860} --workers 1 --worker-class gthread --threads 4 --timeout 120 --keep-alive 5 --access-logfile - --error-logfile - api_server:app"]
