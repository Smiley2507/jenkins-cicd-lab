"""Unit tests for the upstream-facing logic, with no real network calls."""

import pytest
import requests

import weather


class FakeResponse:
    def __init__(self, payload=None, status=200, raise_for_status=None):
        self._payload = payload
        self.status_code = status
        self._raise_for_status = raise_for_status

    def raise_for_status(self):
        if self._raise_for_status:
            raise self._raise_for_status

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


FORECAST_PAYLOAD = {
    "current": {
        "time": "2026-08-20T09:00",
        "temperature_2m": 21.4,
        "relative_humidity_2m": 68,
        "wind_speed_10m": 11.2,
        "weather_code": 3,
    }
}

AQI_PAYLOAD = {"current": {"european_aqi": 34}}


def _stub_get(monkeypatch, forecast=FORECAST_PAYLOAD, aqi=AQI_PAYLOAD):
    """Route forecast and air-quality URLs to separate canned payloads."""

    def fake_get(url, params=None, timeout=None):
        if url == weather.FORECAST_URL:
            if isinstance(forecast, Exception):
                raise forecast
            return FakeResponse(forecast)
        if isinstance(aqi, Exception):
            raise aqi
        return FakeResponse(aqi)

    monkeypatch.setattr(weather.requests, "get", fake_get)


# --- allowlist ------------------------------------------------------------

def test_known_cities_are_sorted_by_name():
    names = [c["name"] for c in weather.known_cities()]
    assert names == sorted(names)
    assert "Kigali" in names


@pytest.mark.parametrize("slug", ["kigali", "KIGALI", "London"])
def test_is_known_city_accepts_allowlisted_slugs_case_insensitively(slug):
    assert weather.is_known_city(slug) is True


@pytest.mark.parametrize("slug", ["atlantis", "", None, 42])
def test_is_known_city_rejects_everything_else(slug):
    assert weather.is_known_city(slug) is False


def test_fetch_weather_rejects_unknown_city_without_network(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("no network call should be made for an unknown city")

    monkeypatch.setattr(weather.requests, "get", explode)

    with pytest.raises(weather.WeatherServiceError, match="Unknown city"):
        weather.fetch_weather("atlantis")


# --- happy path -----------------------------------------------------------

def test_fetch_weather_maps_upstream_payload(monkeypatch):
    _stub_get(monkeypatch)

    result = weather.fetch_weather("kigali")

    assert result["city"] == "Kigali"
    assert result["country"] == "Rwanda"
    assert result["temperature"] == 21.4
    assert result["humidity"] == 68
    assert result["conditions"] == "Overcast"
    assert result["aqi"] == 34
    assert result["aqi_band"]["label"] == "Fair"


# --- upstream failure modes ----------------------------------------------

def test_fetch_weather_wraps_timeout(monkeypatch):
    _stub_get(monkeypatch, forecast=requests.exceptions.Timeout())

    with pytest.raises(weather.WeatherServiceError, match="timed out"):
        weather.fetch_weather("nairobi")


def test_fetch_weather_wraps_connection_error(monkeypatch):
    _stub_get(monkeypatch, forecast=requests.exceptions.ConnectionError("boom"))

    with pytest.raises(weather.WeatherServiceError, match="failed"):
        weather.fetch_weather("nairobi")


def test_fetch_weather_rejects_payload_without_current(monkeypatch):
    _stub_get(monkeypatch, forecast={"latitude": 1.0})

    with pytest.raises(weather.WeatherServiceError, match="no current weather"):
        weather.fetch_weather("lagos")


def test_air_quality_failure_degrades_instead_of_raising(monkeypatch):
    _stub_get(monkeypatch, aqi=requests.exceptions.Timeout())

    result = weather.fetch_weather("dublin")

    assert result["temperature"] == 21.4
    assert result["aqi"] is None
    assert result["aqi_band"]["label"] == "Unavailable"


# --- pure functions -------------------------------------------------------

@pytest.mark.parametrize(
    "code,expected",
    [(0, "Clear sky"), (61, "Slight rain"), (95, "Thunderstorm"), (7777, "Unknown conditions")],
)
def test_describe_weather_code(code, expected):
    assert weather.describe_weather_code(code) == expected


@pytest.mark.parametrize(
    "aqi,label,severity",
    [
        (0, "Good", 1),
        (20, "Good", 1),
        (21, "Fair", 2),
        (40, "Fair", 2),
        (55, "Moderate", 3),
        (75, "Poor", 4),
        (95, "Very poor", 5),
        (140, "Extremely poor", 6),
        (None, "Unavailable", 0),
    ],
)
def test_aqi_band_boundaries(aqi, label, severity):
    band = weather.aqi_band(aqi)
    assert band["label"] == label
    assert band["severity"] == severity


def test_aqi_band_rejects_negative():
    with pytest.raises(weather.WeatherServiceError, match="negative"):
        weather.aqi_band(-5)


def test_aqi_band_rejects_non_numeric():
    with pytest.raises(weather.WeatherServiceError, match="numeric"):
        weather.aqi_band("clean")
