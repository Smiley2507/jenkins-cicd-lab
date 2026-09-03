import os
import time

from flask import Flask, abort, render_template, request
from prometheus_client import CollectorRegistry
from prometheus_flask_exporter import PrometheusMetrics
from logging_config import configure_logging
from tracing import init_tracing

logger = configure_logging()

from weather import (
    WeatherServiceError,
    fetch_weather,
    is_known_city,
    known_cities,
)

APP_VERSION = os.environ.get("APP_VERSION", "dev")


def create_app():
    """Application factory — lets tests build an isolated instance."""
    app = Flask(__name__)
    init_tracing(app, version=APP_VERSION)
    # A fresh registry per app instance: create_app() runs once per test, and
    # re-registering the same metric names on the shared default registry
    # raises "Duplicated timeseries".
    metrics = PrometheusMetrics(app, group_by='endpoint', registry=CollectorRegistry())

    @app.get("/health")
    def health():
        """Liveness probe. Deliberately does no upstream call, so the
        container reports healthy even if Open-Meteo is down."""
        return {"status": "ok", "version": APP_VERSION}, 200

    @app.get("/")
    def index():
        return render_template("index.html", cities=known_cities(), result=None, error=None)

    @app.post("/")
    def lookup():
        slug = (request.form.get("city") or "").strip().lower()

        if not slug:
            return (
                render_template(
                    "index.html", cities=known_cities(), result=None,
                    error="Please choose a city.",
                ),
                400,
            )

        if not is_known_city(slug):
            return (
                render_template(
                    "index.html", cities=known_cities(), result=None,
                    error=f"'{slug}' is not one of the supported cities.",
                ),
                400,
            )

        try:
            result = fetch_weather(slug)
        except WeatherServiceError as exc:
            return (
                render_template(
                    "index.html", cities=known_cities(), result=None,
                    error=f"Could not retrieve weather right now. {exc}",
                ),
                502,
            )

        return render_template("index.html", cities=known_cities(), result=result, error=None)

    @app.after_request
    def log_request(response):
        # One JSON log line per request, carrying the trace ID -- the join
        # key between a Jaeger trace and its CloudWatch log lines.
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
            },
        )
        return response

    if os.environ.get("ENABLE_TEST_ROUTES", "").lower() in ("1", "true", "yes"):

        @app.route("/slow")
        def slow():
            # Past the 300ms alert threshold; sleeping in the handler makes it
            # show up as server-span time, like a real slow endpoint.
            time.sleep(0.8)
            logger.warning("slow endpoint hit", extra={"delay_seconds": 0.8})
            return {"status": "slow"}, 200

        @app.route("/boom")
        def boom():
            logger.error("deliberate failure for alert testing")
            abort(500)

    # Counter, duration histogram and in-progress gauge, labelled by method/path.
    request_labels = {"method": lambda: request.method, "path": lambda: request.path}
    metrics.register_default(
        metrics.counter(
            "weather_app_requests_total", "Total number of requests",
            labels={**request_labels, "status_code": lambda r: r.status_code},
        ),
        metrics.histogram(
            "weather_app_request_duration_seconds", "Request duration in seconds",
            labels=request_labels,
        ),
        metrics.gauge(
            "weather_app_inprogress_requests", "Number of in-progress requests",
            labels=request_labels,
        ),
    )
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)