"""Weather and air-quality lookups against the Open-Meteo public API.

Kept separate from the Flask layer so the network-facing logic can be unit
tested without spinning up a test client.
"""

import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

REQUEST_TIMEOUT = 5

# The scoped allowlist. Anything not in here is rejected before we make a
# network call, which keeps the app from being used as an open proxy.
CITIES = {
    "kigali": {"name": "Kigali", "country": "Rwanda", "lat": -1.9536, "lon": 30.0606},
    "nairobi": {"name": "Nairobi", "country": "Kenya", "lat": -1.2921, "lon": 36.8219},
    "lagos": {"name": "Lagos", "country": "Nigeria", "lat": 6.5244, "lon": 3.3792},
    "cairo": {"name": "Cairo", "country": "Egypt", "lat": 30.0444, "lon": 31.2357},
    "dublin": {"name": "Dublin", "country": "Ireland", "lat": 53.3498, "lon": -6.2603},
    "london": {"name": "London", "country": "United Kingdom", "lat": 51.5072, "lon": -0.1276},
}

# WMO weather interpretation codes, condensed to the ones that actually occur.
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherServiceError(Exception):
    """Raised when the upstream API is unreachable or returns junk."""


def known_cities():
    """City slugs and display names, sorted for stable rendering."""
    return sorted(
        ({"slug": slug, **data} for slug, data in CITIES.items()),
        key=lambda c: c["name"],
    )


def is_known_city(slug):
    return isinstance(slug, str) and slug.lower() in CITIES


def describe_weather_code(code):
    """Map a WMO code to human-readable text."""
    return WEATHER_CODES.get(code, "Unknown conditions")


def aqi_band(aqi):
    """Band a European AQI value into a label and a severity level.

    Bands follow the European AQI scale. Severity is a small integer the
    template uses to pick a colour, so the UI never has to parse the label.
    """
    if aqi is None:
        return {"label": "Unavailable", "severity": 0}
    if not isinstance(aqi, (int, float)):
        raise WeatherServiceError(f"AQI must be numeric, got {type(aqi).__name__}")
    if aqi < 0:
        raise WeatherServiceError(f"AQI cannot be negative, got {aqi}")

    if aqi <= 20:
        return {"label": "Good", "severity": 1}
    if aqi <= 40:
        return {"label": "Fair", "severity": 2}
    if aqi <= 60:
        return {"label": "Moderate", "severity": 3}
    if aqi <= 80:
        return {"label": "Poor", "severity": 4}
    if aqi <= 100:
        return {"label": "Very poor", "severity": 5}
    return {"label": "Extremely poor", "severity": 6}


def _get_json(url, params):
    """Single place where network errors become WeatherServiceError."""
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout as exc:
        raise WeatherServiceError("Upstream weather service timed out") from exc
    except requests.exceptions.RequestException as exc:
        raise WeatherServiceError(f"Upstream weather service failed: {exc}") from exc
    except ValueError as exc:
        raise WeatherServiceError("Upstream returned a malformed response") from exc


def fetch_air_quality(lat, lon):
    """Current European AQI. Returns None rather than raising, so a failure
    here degrades the page instead of breaking it."""
    try:
        payload = _get_json(
            AIR_QUALITY_URL,
            {"latitude": lat, "longitude": lon, "current": "european_aqi"},
        )
        return payload.get("current", {}).get("european_aqi")
    except WeatherServiceError:
        return None


def fetch_weather(slug):
    """Fetch current conditions for an allowlisted city slug."""
    if not is_known_city(slug):
        raise WeatherServiceError(f"Unknown city: {slug}")

    city = CITIES[slug.lower()]
    payload = _get_json(
        FORECAST_URL,
        {
            "latitude": city["lat"],
            "longitude": city["lon"],
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            "timezone": "auto",
        },
    )

    current = payload.get("current")
    if not current:
        raise WeatherServiceError("Upstream response contained no current weather")

    aqi = fetch_air_quality(city["lat"], city["lon"])

    return {
        "city": city["name"],
        "country": city["country"],
        "temperature": current.get("temperature_2m"),
        "humidity": current.get("relative_humidity_2m"),
        "wind_speed": current.get("wind_speed_10m"),
        "conditions": describe_weather_code(current.get("weather_code")),
        "observed_at": current.get("time"),
        "aqi": aqi,
        "aqi_band": aqi_band(aqi),
    }
