import os

from flask import Flask, render_template, request

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

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
