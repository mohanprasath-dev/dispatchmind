"""Weather MCP Server for DispatchMind.

Provides weather forecasting and rain risk detection for routes using the
Open-Meteo free API with deterministic Chennai weather simulation fallback.
Wrapped with resilience for self-healing execution.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import httpx

from fastmcp import FastMCP
from core.config import OPEN_METEO_BASE_URL
from core.resilience import resilient

mcp = FastMCP("WeatherServer")


def fallback_forecast_for_point(lat: float, lng: float) -> Dict[str, Any]:
    """Deterministic simulated weather for Chennai and southern India coordinates."""
    # Predictable, pleasant tropical day in Chennai
    return {
        "latitude": round(lat, 4),
        "longitude": round(lng, 4),
        "temperature_c": 31.5,
        "relative_humidity": 68,
        "wind_speed_kmh": 14.0,
        "precipitation_probability": 15,
        "precipitation_mm": 0.0,
        "weather_code": 1,
        "condition": "Mainly clear",
        "source": "simulated_fallback",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def fallback_rain_risk(lat: float, lng: float, window_hours: int = 3) -> Dict[str, Any]:
    """Deterministic fallback rain risk calculation."""
    # Under fallback, return low baseline risk for standard operations
    prob = 15
    precip = 0.0
    return {
        "latitude": round(lat, 4),
        "longitude": round(lng, 4),
        "window_hours": window_hours,
        "rain_probability": prob,
        "precipitation_mm": precip,
        "has_risk": False,
        "warning_level": "none",
        "source": "simulated_fallback",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@mcp.tool()
@resilient(fallback=fallback_forecast_for_point, retries=2)
def forecast_for_point(lat: float, lng: float) -> Dict[str, Any]:
    """Get current and short-term weather forecast for a geographic point.

    Args:
        lat: Latitude coordinate.
        lng: Longitude coordinate.

    Returns:
        Dict containing temperature, precipitation probability, humidity, and condition.
    """
    url = f"{OPEN_METEO_BASE_URL.rstrip('/')}/forecast"
    params = {
        "latitude": lat,
        "longitude": lng,
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "hourly": "precipitation_probability,precipitation",
        "timezone": "auto",
        "forecast_days": 1,
    }

    with httpx.Client(timeout=6.0) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        current = data.get("current", {})
        hourly = data.get("hourly", {})
        precip_probs = hourly.get("precipitation_probability", [0])
        next_prob = precip_probs[0] if precip_probs else 0

        # WMO Weather interpretation code mapping
        wmo_code = current.get("weather_code", 0)
        condition = "Clear"
        if wmo_code in [1, 2, 3]:
            condition = "Partly cloudy"
        elif wmo_code in [45, 48]:
            condition = "Foggy"
        elif wmo_code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
            condition = "Rain"
        elif wmo_code in [95, 96, 99]:
            condition = "Thunderstorm"

        return {
            "latitude": lat,
            "longitude": lng,
            "temperature_c": current.get("temperature_2m", 30.0),
            "relative_humidity": current.get("relative_humidity_2m", 65),
            "wind_speed_kmh": current.get("wind_speed_10m", 12.0),
            "precipitation_probability": next_prob,
            "precipitation_mm": current.get("precipitation", 0.0),
            "weather_code": wmo_code,
            "condition": condition,
            "source": "open_meteo_api",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@mcp.tool()
@resilient(fallback=fallback_rain_risk, retries=2)
def rain_risk(lat: float, lng: float, window_hours: int = 3) -> Dict[str, Any]:
    """Evaluate rain and monsoon risk for a delivery location over the next few hours.

    Args:
        lat: Latitude coordinate.
        lng: Longitude coordinate.
        window_hours: Lookahead window in hours (default: 3).

    Returns:
        Dict with 'rain_probability', 'precipitation_mm', 'has_risk', and 'warning_level'.
    """
    url = f"{OPEN_METEO_BASE_URL.rstrip('/')}/forecast"
    params = {
        "latitude": lat,
        "longitude": lng,
        "hourly": "precipitation_probability,precipitation",
        "timezone": "auto",
        "forecast_days": 1,
    }

    with httpx.Client(timeout=6.0) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        hourly = data.get("hourly", {})
        probs = hourly.get("precipitation_probability", [])[:max(1, window_hours)]
        precips = hourly.get("precipitation", [])[:max(1, window_hours)]

        max_prob = max(probs) if probs else 0
        total_precip = sum(precips) if precips else 0.0

        # Assess risk thresholds
        has_risk = max_prob >= 40 or total_precip >= 1.0
        warning_level = "none"
        if max_prob >= 75 or total_precip >= 5.0:
            warning_level = "high"
        elif max_prob >= 40 or total_precip >= 1.0:
            warning_level = "moderate"
        elif max_prob >= 20:
            warning_level = "low"

        return {
            "latitude": lat,
            "longitude": lng,
            "window_hours": window_hours,
            "rain_probability": max_prob,
            "precipitation_mm": round(total_precip, 2),
            "has_risk": has_risk,
            "warning_level": warning_level,
            "source": "open_meteo_api",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


if __name__ == "__main__":
    mcp.run()
