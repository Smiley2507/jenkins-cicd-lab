"""Route-level tests using the Flask test client."""

import pytest

import app as app_module
import weather


@pytest.fixture
def client():
    application = app_module.create_app()
    application.config.update(TESTING=True)
    with application.test_client() as test_client:
        yield test_client


SAMPLE_RESULT = {
    "city": "Kigali",
    "country": "Rwanda",
    "temperature": 21.4,
    "humidity": 68,
    "wind_speed": 11.2,
    "conditions": "Overcast",
    "observed_at": "2026-08-20T09:00",
    "aqi": 34,
    "aqi_band": {"label": "Fair", "severity": 2},
}


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
    assert "version" in response.get_json()


def test_index_renders_the_city_form(client):
    response = client.get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Kigali" in body
    assert "<form" in body


def test_lookup_renders_weather_for_a_valid_city(client, monkeypatch):
    monkeypatch.setattr(app_module, "fetch_weather", lambda slug: SAMPLE_RESULT)

    response = client.post("/", data={"city": "kigali"})

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "21.4" in body
    assert "Overcast" in body
    assert "Fair" in body


def test_lookup_rejects_unknown_city(client):
    response = client.post("/", data={"city": "atlantis"})

    assert response.status_code == 400
    assert "not one of the supported cities" in response.get_data(as_text=True)


def test_lookup_requires_a_city(client):
    response = client.post("/", data={})

    assert response.status_code == 400
    assert "Please choose a city" in response.get_data(as_text=True)


def test_lookup_returns_502_when_upstream_fails(client, monkeypatch):
    def boom(slug):
        raise weather.WeatherServiceError("Upstream weather service timed out")

    monkeypatch.setattr(app_module, "fetch_weather", boom)

    response = client.post("/", data={"city": "london"})

    assert response.status_code == 502
    assert "Could not retrieve weather" in response.get_data(as_text=True)


# # --- observability --------------------------------------------------------

# def test_metrics_endpoint_is_exposed(client):
#     """Prometheus scrapes this. If it 404s, every dashboard is empty."""
#     response = client.get("/metrics")

#     assert response.status_code == 200
#     body = response.get_data(as_text=True)
#     assert "flask_http_request_duration_seconds" in body
#     assert "weather_app_info" in body


# def test_requests_are_counted_by_status(client):
#     """A request must show up in the counter, labelled with its status."""
#     client.get("/health")

#     body = client.get("/metrics").get_data(as_text=True)

#     assert 'flask_http_request_total{method="GET",status="200"}' in body