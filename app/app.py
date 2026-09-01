import os

from flask import Flask, render_template, request
from prometheus_flask_exporter import PrometheusMetrics

from weather import (
    WeatherServiceError,
    fetch_weather,
    is_known_city,
    known_cities,
)

APP_VERSION = os.environ.get("APP_VERSION", "dev")


# def _attach_metrics(app):
    
#     if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
#         from prometheus_flask_exporter.multiprocess import GunicornPrometheusMetrics

#         # The multiprocess collector builds its own registry from the shared
#         # directory, so it must not be given one.
#         metrics = GunicornPrometheusMetrics(app)
#         metrics.register_endpoint("/metrics", app)
#     else:
#         from prometheus_client import CollectorRegistry
#         from prometheus_flask_exporter import PrometheusMetrics

#         # A registry per application instance rather than the global default.
#         # create_app() is called once per test, and re-registering the same
#         # metric names in one shared registry raises "Duplicated timeseries".
#         metrics = PrometheusMetrics(app, registry=CollectorRegistry())

#     # A constant-value metric carrying the build tag as a label, so Grafana can
#     # show which version produced a given series.
#     metrics.info("weather_app_info", "Application metadata", version=APP_VERSION)
#     return metrics


def create_app():
    """Application factory — lets tests build an isolated instance."""
    app = Flask(__name__)
    metrics = PrometheusMetrics(app, group_by='endpoint')

    # Registers /metrics and instruments every request with a duration
    # histogram and a counter labelled by status, method and path.
    # _attach_metrics(app)

    @app.get("/health")
    def health():
        """Liveness probe. Deliberately does no upstream call, so the
        container reports healthy even if Open-Meteo is down."""
        return {"status": "ok", "version": APP_VERSION}, 200

    @app.get("/")
    def index():
        print(str(request.environ.get('werkzeug.request').response.status_code))
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

    
    metrics.register_default(
            metrics.counter(
                'weather_app_requests_total', 'Total number of requests', labels={'method': lambda: request.method,'path': lambda: request.path, 'status_code': lambda r: r.status_code}
            )
            metrics.histogram(
                'weather_app_request_duration_seconds', 'Request duration in seconds', labels={'method': lambda: request.method,'path': lambda: request.path}
            )
            metrics.gauge(
                'weather_app_inprogress_requests', 'Number of in-progress requests', labels={'method': lambda: request.method,'path': lambda: request.path}
            )
    )
    return app



app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)