# syntax=docker/dockerfile:1

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
    PYTHONUNBUFFERED=1 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc

# Run as a non-root user. Nothing in this image needs to write to disk.
RUN useradd --create-home --shell /usr/sbin/nologin appuser

# Shared directory for the Prometheus multiprocess collector. Every gunicorn
# worker writes its samples here and they are aggregated on scrape.
RUN mkdir -p /tmp/prometheus_multiproc && chown appuser:appuser /tmp/prometheus_multiproc

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY app.py weather.py gunicorn.conf.py ./
COPY templates ./templates

USER appuser

# Not published to the host — nginx is the only thing that talks to this port.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status == 200 else 1)"

# Settings live in gunicorn.conf.py, which also carries the two hooks the
# Prometheus multiprocess collector needs.
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]