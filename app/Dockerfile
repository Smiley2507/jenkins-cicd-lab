# syntax=docker/dockerfile:1
#
# Build context is THIS directory, not the repo root:
#   docker build -t weather-app:local --build-arg APP_VERSION=local app/
#
# Keeping the Dockerfile beside the code it builds means terraform/ and
# ansible/ are structurally outside the context — they can't leak into a build
# even if .dockerignore is wrong.

# --- build stage: resolve dependencies into a wheel cache -------------------
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# --- runtime stage ---------------------------------------------------------
FROM python:3.12-slim

# Stamped by the pipeline: --build-arg APP_VERSION=${BUILD_NUMBER}-${SHORT_COMMIT}
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Run as a non-root user. Nothing in this image needs to write to disk.
RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY app.py weather.py ./
COPY templates ./templates

USER appuser

# Not published to the host — nginx is the only thing that talks to this port.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status == 200 else 1)"

# Two workers suits a t3.small. Access logs to stdout for the json-file driver.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "app:app"]
