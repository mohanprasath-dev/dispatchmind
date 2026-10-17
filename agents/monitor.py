"""Monitor Agent for DispatchMind.

Performs real-time fleet route health checks:
- Compares live ETA vs planned ETA for active/in-transit stops
- Detects rain/weather risks along delivery corridors
- Flags idle drivers exceeding idle threshold
- Emits Alert models and logs them to store.events
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from core.config import MONITOR_INTERVAL_SEC, DEMO_MODE, OPEN_METEO_BASE_URL
from core.models import Alert, RoutePlan, VehicleRoute, Stop
from core.resilience import resilient, log_resilience_event
from core.store import store

logger = logging.getLogger(__name__)


def _parse_minutes(time_str: str) -> int:
    """Parse HH:MM or ISO timestamp to minutes from midnight."""
    if not time_str:
        return 0
    clean = time_str.strip()
    if "T" in clean:
        clean = clean.split("T")[-1]
    if ":" in clean:
        parts = clean.split(":")
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except Exception:
            return 0
    return 0


@resilient(retries=2, base_delay=0.01)
def check_weather_rain_risk(lat: float, lng: float) -> Optional[str]:
    """Check rain risk for coordinates. In demo mode or offline, use deterministic fallback."""
    if DEMO_MODE:
        # In demo mode, simulate based on known test scenario or clear weather
        return None
    try:
        import httpx
        url = f"{OPEN_METEO_BASE_URL}/forecast"
        params = {
            "latitude": lat,
            "longitude": lng,
            "hourly": "precipitation_probability,precipitation",
            "forecast_days": 1,
        }
        resp = httpx.get(url, params=params, timeout=3.0)
        if resp.status_code == 200:
            data = resp.json()
            precip_prob = data.get("hourly", {}).get("precipitation_probability", [0])
            if precip_prob and max(precip_prob[:6]) > 60:
                return "Heavy rain predicted along delivery route"
    except Exception as exc:
        logger.warning(f"Weather check failed for {lat},{lng}: {exc}")
    return None


def check_active_routes(
    routes: Optional[List[VehicleRoute]] = None,
    vehicles_state: Optional[List[Dict[str, Any]]] = None,
) -> List[Alert]:
    """
    Check all active routes for anomalies:
    1. ETA drift > 15 minutes between live estimated ETA and planned ETA.
    2. Rain risk detected on route corridor.
    3. Driver idle > 20 minutes while on route.
    """
    alerts: List[Alert] = []

    # 1. Fetch routes if not provided
    if routes is None:
        raw_routes = store.list("routes")
        routes_list: List[VehicleRoute] = []
        for r in raw_routes:
            if isinstance(r, dict):
                # Could be a master RoutePlan or VehicleRoute directly
                if "routes" in r and isinstance(r["routes"], list):
                    for sub_r in r["routes"]:
                        routes_list.append(VehicleRoute(**sub_r) if isinstance(sub_r, dict) else sub_r)
                else:
                    routes_list.append(VehicleRoute(**r))
            elif isinstance(r, VehicleRoute):
                routes_list.append(r)
        routes = routes_list

    # 2. Check each vehicle route
    for route in routes:
        v_id = route.vehicle_id

        # Check stops
        for stop in route.stops:
            if stop.status in ("completed", "delivered"):
                continue

            # Check ETA drift
            planned = stop.planned_eta or stop.eta
            live = stop.eta
            if planned and live:
                p_min = _parse_minutes(planned)
                l_min = _parse_minutes(live)
                drift = l_min - p_min
                if drift > 15:
                    alert = Alert(
                        alert_id=f"alt_{uuid.uuid4().hex[:8]}",
                        vehicle_id=v_id,
                        order_id=stop.order_id,
                        alert_type="ETA_DRIFT",
                        severity="WARNING",
                        drift_minutes=drift,
                        message=f"Vehicle {v_id} order {stop.order_id} delayed by {drift} minutes against planned ETA.",
                    )
                    alerts.append(alert)
                    store.set("events", alert.alert_id, {
                        "event_id": alert.alert_id,
                        "event_type": "alert_created",
                        "source": "monitor",
                        "details": alert.model_dump(),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

            # Check weather / rain risk at stop coordinates
            if stop.lat and stop.lng:
                rain_risk = check_weather_rain_risk(stop.lat, stop.lng)
                if rain_risk:
                    alert = Alert(
                        alert_id=f"alt_{uuid.uuid4().hex[:8]}",
                        vehicle_id=v_id,
                        order_id=stop.order_id,
                        alert_type="WEATHER_RISK",
                        severity="WARNING",
                        weather_condition=rain_risk,
                        message=f"Weather risk for vehicle {v_id} at stop {stop.order_id}: {rain_risk}",
                    )
                    alerts.append(alert)
                    store.set("events", alert.alert_id, {
                        "event_id": alert.alert_id,
                        "event_type": "alert_created",
                        "source": "monitor",
                        "details": alert.model_dump(),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

    # 3. Check vehicles for idle state > 20 minutes
    if vehicles_state is not None:
        v_list = vehicles_state
    else:
        v_list = store.list("vehicles")

    for v in v_list:
        v_id = v.get("id")
        idle_min = v.get("idle_minutes", 0)
        status = v.get("status", "").lower()
        # If on_route or busy, and idle_minutes > 20
        if idle_min > 20:
            alert = Alert(
                alert_id=f"alt_{uuid.uuid4().hex[:8]}",
                vehicle_id=v_id,
                alert_type="DRIVER_IDLE",
                severity="WARNING",
                idle_minutes=idle_min,
                message=f"Driver for vehicle {v_id} stationary for {idle_min} minutes without delivery progress.",
            )
            alerts.append(alert)
            store.set("events", alert.alert_id, {
                "event_id": alert.alert_id,
                "event_type": "alert_created",
                "source": "monitor",
                "details": alert.model_dump(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    return alerts


def build_agent():
    """Build and export Google ADK Monitor Agent."""
    from google.adk.agents import Agent

    def monitor_tool() -> str:
        """Scan active routes for ETA drift, rain risks, and idle drivers."""
        alerts = check_active_routes()
        return json.dumps([a.model_dump() for a in alerts])

    agent = Agent(
        name="monitor",
        model="gemini-2.5-flash",
        description="Continuous monitoring agent for route health, ETA drift, and corridor risks.",
        instruction=(
            "You are the Monitor Agent for DispatchMind. "
            "You continuously observe fleet operations across Indian city corridors. "
            "Scan for delays exceeding 15 minutes, weather/rain risk, and idle vehicles exceeding 20 minutes. "
            "Report alerts concisely without using em dashes."
        ),
        tools=[monitor_tool],
    )
    return agent
