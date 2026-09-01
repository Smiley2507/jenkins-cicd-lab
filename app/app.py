import os

from flask import Flask, render_template, request
from prometheus_client import CollectorRegistry
from prometheus_flask_exporter import PrometheusMetrics

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

    @app.get("/boom")
    def boom():
        """Always raises, so 500 handling and error alerting can be tested."""
        raise RuntimeError("boom: intentional failure for testing error paths")

    # Request counter, duration histogram and in-progress gauge, each labelled
    # by method and path (the counter also carries the response status code).
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