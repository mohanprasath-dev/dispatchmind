"""Maps MCP Server for DispatchMind.

Provides geocoding, distance matrix calculation, and ETA computations.
Works reliably in DEMO_MODE or without GOOGLE_MAPS_API_KEY via haversine
and Chennai pincode fallbacks. All tools are resiliently wrapped.
"""

import math
import os
import re
from typing import Any, Dict, List, Optional
import httpx

from fastmcp import FastMCP
from core.config import (
    DEMO_MODE,
    DEPOT_LAT,
    DEPOT_LNG,
    GOOGLE_MAPS_API_KEY,
)
from core.resilience import resilient

mcp = FastMCP("MapsServer")

# Known Chennai area and pincode coordinate mapping for offline and demo fallback
CHENNAI_PINCODE_COORDINATES: Dict[str, Dict[str, Any]] = {
    "600001": {"lat": 13.0933, "lng": 80.2872, "locality": "George Town, Chennai"},
    "600002": {"lat": 13.0673, "lng": 80.2707, "locality": "Anna Salai, Chennai"},
    "600004": {"lat": 13.0336, "lng": 80.2678, "locality": "Mylapore, Chennai"},
    "600008": {"lat": 13.0732, "lng": 80.2609, "locality": "Egmore, Chennai"},
    "600017": {"lat": 13.0418, "lng": 80.2341, "locality": "T. Nagar, Chennai"},
    "600018": {"lat": 13.0354, "lng": 80.2458, "locality": "Alwarpet, Chennai"},
    "600020": {"lat": 13.0012, "lng": 80.2565, "locality": "Adyar, Chennai"},
    "600028": {"lat": 13.0238, "lng": 80.2619, "locality": "R.A. Puram, Chennai"},
    "600032": {"lat": 13.0067, "lng": 80.2025, "locality": "Guindy, Chennai"},
    "600034": {"lat": 13.0620, "lng": 80.2420, "locality": "Nungambakkam, Chennai"},
    "600040": {"lat": 13.0850, "lng": 80.2100, "locality": "Anna Nagar, Chennai"},
    "600041": {"lat": 12.9830, "lng": 80.2594, "locality": "Thiruvanmiyur, Chennai"},
    "600042": {"lat": 12.9750, "lng": 80.2210, "locality": "Velachery, Chennai"},
    "600083": {"lat": 13.0340, "lng": 80.2130, "locality": "Ashok Nagar, Chennai"},
    "600096": {"lat": 12.9698, "lng": 80.2450, "locality": "Perungudi, Chennai"},
    "600097": {"lat": 12.9350, "lng": 80.2300, "locality": "Thoraipakkam, Chennai"},
}

LOCALITY_KEYWORDS: Dict[str, Dict[str, Any]] = {
    "t. nagar": {"lat": 13.0418, "lng": 80.2341, "formatted_address": "T. Nagar, Chennai, Tamil Nadu 600017"},
    "t nagar": {"lat": 13.0418, "lng": 80.2341, "formatted_address": "T. Nagar, Chennai, Tamil Nadu 600017"},
    "adyar": {"lat": 13.0012, "lng": 80.2565, "formatted_address": "Adyar, Chennai, Tamil Nadu 600020"},
    "velachery": {"lat": 12.9750, "lng": 80.2210, "formatted_address": "Velachery, Chennai, Tamil Nadu 600042"},
    "mylapore": {"lat": 13.0336, "lng": 80.2678, "formatted_address": "Mylapore, Chennai, Tamil Nadu 600004"},
    "guindy": {"lat": 13.0067, "lng": 80.2025, "formatted_address": "Guindy, Chennai, Tamil Nadu 600032"},
    "anna nagar": {"lat": 13.0850, "lng": 80.2100, "formatted_address": "Anna Nagar, Chennai, Tamil Nadu 600040"},
    "alwarpet": {"lat": 13.0354, "lng": 80.2458, "formatted_address": "Alwarpet, Chennai, Tamil Nadu 600018"},
    "perungudi": {"lat": 12.9698, "lng": 80.2450, "formatted_address": "Perungudi, Chennai, Tamil Nadu 600096"},
    "thiruvanmiyur": {"lat": 12.9830, "lng": 80.2594, "formatted_address": "Thiruvanmiyur, Chennai, Tamil Nadu 600041"},
    "egmore": {"lat": 13.0732, "lng": 80.2609, "formatted_address": "Egmore, Chennai, Tamil Nadu 600008"},
    "george town": {"lat": 13.0933, "lng": 80.2872, "formatted_address": "George Town, Chennai, Tamil Nadu 600001"},
}


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate great circle distance in km between two points."""
    r = 6371.0  # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def road_distance_km(lat1: float, lng1: float, lat2: float, lng2: float, road_factor: float = 1.4) -> float:
    """Estimate realistic road driving distance using haversine x road factor."""
    straight = haversine_distance(lat1, lng1, lat2, lng2)
    return round(straight * road_factor, 2)


def fallback_geocode(address: str) -> Dict[str, Any]:
    """Offline/fallback geocode using regex extraction and Chennai lookup tables."""
    addr_lower = (address or "").lower()

    # Match 6-digit Indian pincode
    pin_match = re.search(r"\b(600\d{3})\b", addr_lower)
    if pin_match:
        pin = pin_match.group(1)
        if pin in CHENNAI_PINCODE_COORDINATES:
            coord = CHENNAI_PINCODE_COORDINATES[pin]
            return {
                "lat": coord["lat"],
                "lng": coord["lng"],
                "formatted_address": f"{address.strip()} (matched {pin})",
                "source": "pincode_fallback",
            }

    # Match known Chennai localities
    for kw, data in LOCALITY_KEYWORDS.items():
        if kw in addr_lower:
            return {
                "lat": data["lat"],
                "lng": data["lng"],
                "formatted_address": data["formatted_address"],
                "source": "locality_fallback",
            }

    # Default to central Chennai depot
    return {
        "lat": DEPOT_LAT,
        "lng": DEPOT_LNG,
        "formatted_address": f"{address.strip()}, Chennai (default depot fallback)",
        "source": "depot_fallback",
    }


def _extract_coord(point: Any) -> tuple[float, float]:
    """Helper to extract (lat, lng) from dict or tuple/list."""
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        return float(point[0]), float(point[1])
    if isinstance(point, dict):
        lat = point.get("lat") or point.get("latitude")
        lng = point.get("lng") or point.get("longitude")
        if lat is not None and lng is not None:
            return float(lat), float(lng)
    raise ValueError(f"Cannot extract coordinates from point: {point}")


def fallback_distance_matrix(origins: List[Any], destinations: List[Any]) -> Dict[str, Any]:
    """Compute distance matrix using haversine * 1.4 road factor and 25 km/h city speed."""
    matrix_distances = []
    matrix_durations = []

    parsed_origins = [_extract_coord(o) for o in origins]
    parsed_dests = [_extract_coord(d) for d in destinations]

    avg_speed_kmh = 25.0

    for o_lat, o_lng in parsed_origins:
        dist_row = []
        dur_row = []
        for d_lat, d_lng in parsed_dests:
            km = road_distance_km(o_lat, o_lng, d_lat, d_lng, road_factor=1.4)
            dur_min = round((km / avg_speed_kmh) * 60.0, 1)
            dist_row.append(km)
            dur_row.append(dur_min)
        matrix_distances.append(dist_row)
        matrix_durations.append(dur_row)

    return {
        "distances_km": matrix_distances,
        "durations_min": matrix_durations,
        "source": "haversine_fallback",
    }


@mcp.tool()
@resilient(fallback=fallback_geocode, retries=2)
def geocode(address: str) -> Dict[str, Any]:
    """Geocode an address to latitude, longitude, and formatted address.

    Args:
        address: Delivery street address or pincode string.

    Returns:
        Dict with 'lat', 'lng', 'formatted_address', and 'source'.
    """
    key = GOOGLE_MAPS_API_KEY
    if DEMO_MODE or not key:
        return fallback_geocode(address)

    # Call Google Maps Geocoding API if key is configured
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    with httpx.Client(timeout=5.0) as client:
        resp = client.get(url, params={"address": address, "key": key})
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "OK" and data.get("results"):
            top = data["results"][0]
            loc = top["geometry"]["location"]
            return {
                "lat": float(loc["lat"]),
                "lng": float(loc["lng"]),
                "formatted_address": top.get("formatted_address", address),
                "source": "google_maps_api",
            }
        # Fall back if Google returns ZERO_RESULTS or other status
        return fallback_geocode(address)


@mcp.tool()
@resilient(fallback=fallback_distance_matrix, retries=2)
def distance_matrix(origins: List[Any], destinations: List[Any]) -> Dict[str, Any]:
    """Compute distance (km) and travel duration (minutes) between points.

    Args:
        origins: List of origin coordinate pairs (dicts or [lat, lng]).
        destinations: List of destination coordinate pairs.

    Returns:
        Dict with 'distances_km' (2D list) and 'durations_min' (2D list).
    """
    key = GOOGLE_MAPS_API_KEY
    if DEMO_MODE or not key:
        return fallback_distance_matrix(origins, destinations)

    # Routes API or Distance Matrix API call when key is present
    try:
        parsed_origins = [_extract_coord(o) for o in origins]
        parsed_dests = [_extract_coord(d) for d in destinations]
        origins_str = "|".join(f"{lat},{lng}" for lat, lng in parsed_origins)
        dests_str = "|".join(f"{lat},{lng}" for lat, lng in parsed_dests)

        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(
                url,
                params={"origins": origins_str, "destinations": dests_str, "key": key},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "OK":
                rows = data.get("rows", [])
                dist_matrix = []
                dur_matrix = []
                for row in rows:
                    r_dist = []
                    r_dur = []
                    for elem in row.get("elements", []):
                        if elem.get("status") == "OK":
                            meters = elem["distance"]["value"]
                            seconds = elem["duration"]["value"]
                            r_dist.append(round(meters / 1000.0, 2))
                            r_dur.append(round(seconds / 60.0, 1))
                        else:
                            r_dist.append(0.0)
                            r_dur.append(0.0)
                    dist_matrix.append(r_dist)
                    dur_matrix.append(r_dur)
                return {
                    "distances_km": dist_matrix,
                    "durations_min": dur_matrix,
                    "source": "google_maps_api",
                }
    except Exception:
        pass

    return fallback_distance_matrix(origins, destinations)


def fallback_eta_between(lat1: float, lng1: float, lat2: float, lng2: float) -> Dict[str, Any]:
    """Deterministic fallback for ETA between two points."""
    km = road_distance_km(lat1, lng1, lat2, lng2, road_factor=1.4)
    avg_speed_kmh = 25.0
    eta_min = round((km / avg_speed_kmh) * 60.0, 1)
    return {
        "km": km,
        "eta_minutes": eta_min,
        "source": "haversine_fallback",
    }


@mcp.tool()
@resilient(fallback=fallback_eta_between, retries=2)
def eta_between(lat1: float, lng1: float, lat2: float, lng2: float) -> Dict[str, Any]:
    """Compute distance in km and estimated arrival time in minutes between two points.

    Args:
        lat1: Origin latitude.
        lng1: Origin longitude.
        lat2: Destination latitude.
        lng2: Destination longitude.

    Returns:
        Dict with 'km' and 'eta_minutes'.
    """
    key = GOOGLE_MAPS_API_KEY
    if DEMO_MODE or not key:
        return fallback_eta_between(lat1, lng1, lat2, lng2)

    try:
        mat = distance_matrix(origins=[{"lat": lat1, "lng": lng1}], destinations=[{"lat": lat2, "lng": lng2}])
        if isinstance(mat, dict) and "distances_km" in mat and mat["distances_km"]:
            km = mat["distances_km"][0][0]
            mins = mat["durations_min"][0][0]
            return {
                "km": km,
                "eta_minutes": mins,
                "source": mat.get("source", "google_maps_api"),
            }
    except Exception:
        pass

    return fallback_eta_between(lat1, lng1, lat2, lng2)


if __name__ == "__main__":
    mcp.run()
