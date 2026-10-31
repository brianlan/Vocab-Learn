FROM python:3.11-slim-bookworm
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" -r requirements.txt
RUN useradd --uid 10001 --create-home app && mkdir /data /audio && chown app:app /data /audio /app && chmod 700 /audio
COPY --chown=app:app . .
USER app
ENV APP_DATA_DIR=/data AUDIO_DIR=/audio
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=collectstatic-build-only python manage.py collectstatic --noinput
ENV DJANGO_DEBUG=0 APP_DATA_DIR=/data AUDIO_DIR=/audio
EXPOSE 8000
CMD ["gunicorn", "vocab.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "60", "--access-logfile", "-"]
