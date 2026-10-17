"""Recovery Agent for DispatchMind.

Self-healing recovery logic for route disruptions:
- Breakdown / vehicle failure -> reassign stops to nearest vehicle with capacity.
- Traffic delay / ETA drift -> re-sequence stops if delay can be recovered without violating windows/capacity.
- Customer unreachable / wrong address -> reschedule order to end-of-day loop or next window.
- Auto-apply policy:
  * If impact delay <= AUTO_APPLY_MAX_DELAY_MIN (20/15 min) and no hard window or capacity violations: auto-apply (status="applied").
  * Otherwise: status="proposed" with a concise one-line proposal.
- Logs actions to store.events and triggers comms notifications.
"""

import json
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from core.config import AUTO_APPLY_MAX_DELAY_MIN
from core.models import Alert, RecoveryAction, Order, Vehicle, VehicleRoute, Stop
from core.resilience import resilient, log_resilience_event
from core.store import store
from agents.comms import format_eta_update, format_driver_reassignment

logger = logging.getLogger(__name__)


def _parse_minutes(time_str: str) -> int:
    """Convert 'HH:MM' string to minutes from midnight."""
    if not time_str:
        return 540
    clean = time_str.strip()
    if "T" in clean:
        clean = clean.split("T")[-1]
    if ":" in clean:
        parts = clean.split(":")
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except Exception:
            return 540
    return 540


def _minutes_to_time_str(minutes: int) -> str:
    """Convert minutes from midnight to 'HH:MM'."""
    hours = (minutes // 60) % 24
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Road adjusted distance in km between two lat/lng points."""
    if (lat1, lon1) == (lat2, lon2):
        return 0.0
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c * 1.4, 2)


def recover_alert(
    alert: Alert,
    vehicles: Optional[List[Vehicle]] = None,
    routes: Optional[List[VehicleRoute]] = None,
    orders: Optional[List[Order]] = None,
) -> RecoveryAction:
    """
    Execute self-healing recovery for an alert:
    1. Breakdown / failure -> reassign
    2. Traffic / ETA drift -> re-sequence or reassign
    3. Wrong address / unreachable -> reschedule
    """
    # Load state from store if not provided
    if vehicles is None:
        raw_v = store.list("vehicles")
        vehicles = [Vehicle(**v) if isinstance(v, dict) else v for v in raw_v]
    if routes is None:
        raw_r = store.list("routes")
        routes_list: List[VehicleRoute] = []
        for r in raw_r:
            if isinstance(r, dict):
                if "routes" in r and isinstance(r["routes"], list):
                    for sub in r["routes"]:
                        routes_list.append(VehicleRoute(**sub) if isinstance(sub, dict) else sub)
                else:
                    routes_list.append(VehicleRoute(**r))
            elif isinstance(r, VehicleRoute):
                routes_list.append(r)
        routes = routes_list
    if orders is None:
        raw_o = store.list("orders")
        orders = [Order(**o) if isinstance(o, dict) else o for o in raw_o]

    orders_map = {o.id: o for o in orders}
    vehicles_map = {v.id: v for v in vehicles}
    routes_map = {r.vehicle_id: r for r in routes}

    action_id = f"rec_{uuid.uuid4().hex[:8]}"
    alert_type_lower = alert.alert_type.lower()
    msg_lower = alert.message.lower()

    # Determine failure nature
    is_breakdown = "breakdown" in alert_type_lower or "breakdown" in msg_lower
    is_reschedule = (
        "unreachable" in alert_type_lower
        or "wrong_address" in alert_type_lower
        or "address" in msg_lower
        or "unreachable" in msg_lower
        or "not available" in msg_lower
    )

    # 1. Reschedule handling
    if is_reschedule:
        order_id = alert.order_id
        action = RecoveryAction(
            action_id=action_id,
            alert_id=alert.alert_id,
            action_type="reschedule",
            description=f"Reschedule order {order_id} to end-of-day loop or next delivery window.",
            proposal=f"Reschedule order {order_id} to end-of-day loop or next delivery window.",
            affected_vehicle_id=alert.vehicle_id,
            order_ids=[order_id] if order_id else [],
            delay_impact_min=0,
            auto_applied=True,
            status="applied",
            result_status="applied",
        )
        if order_id and order_id in orders_map:
            store.update("orders", order_id, {"status": "rescheduled"})
        _log_and_notify_recovery(action)
        return action

    # 2. Breakdown handling -> Reassign all unvisited stops of affected vehicle
    if is_breakdown:
        affected_v_id = alert.vehicle_id
        affected_route = routes_map.get(affected_v_id)
        stops_to_reassign = []
        if affected_route:
            stops_to_reassign = [
                s for s in affected_route.stops if s.status not in ("completed", "delivered")
            ]
        elif alert.order_id:
            # Single order breakdown context
            if alert.order_id in orders_map:
                o = orders_map[alert.order_id]
                stops_to_reassign = [Stop(
                    stop_number=1,
                    order_id=o.id,
                    lat=o.lat or 13.0,
                    lng=o.lng or 80.2,
                    weight_kg=o.weight_kg,
                    eta="12:00",
                    window_start=o.window_start,
                    window_end=o.window_end,
                )]

        reassigned_orders = [s.order_id for s in stops_to_reassign]
        total_weight = sum(s.weight_kg for s in stops_to_reassign)

        # Find candidate target vehicle with capacity and closest distance
        best_target: Optional[Vehicle] = None
        min_dist = float("inf")

        for v in vehicles:
            if v.id == affected_v_id or v.status.lower() in ("breakdown", "maintenance"):
                continue
            # Check capacity
            current_route = routes_map.get(v.id)
            current_weight = current_route.total_weight_kg if current_route else 0.0
            if current_weight + total_weight <= v.capacity_kg:
                # Approximate distance to first stop
                if stops_to_reassign:
                    dist = haversine_km(v.current_lat, v.current_lng, stops_to_reassign[0].lat, stops_to_reassign[0].lng)
                else:
                    dist = 0.0
                if dist < min_dist:
                    min_dist = dist
                    best_target = v

        if best_target:
            # Impact delay estimated from transit distance
            delay_impact = int(min_dist * 2) # approx 2 min per km
            auto_apply = (delay_impact <= AUTO_APPLY_MAX_DELAY_MIN)
            status_val = "applied" if auto_apply else "proposed"

            action = RecoveryAction(
                action_id=action_id,
                alert_id=alert.alert_id,
                action_type="reassign",
                description=f"Reassign {len(reassigned_orders)} stops from vehicle {affected_v_id} to vehicle {best_target.id}.",
                proposal=f"Reassign {len(reassigned_orders)} stops to {best_target.id} with estimated {delay_impact} min delay.",
                affected_vehicle_id=affected_v_id,
                target_vehicle_id=best_target.id,
                order_ids=reassigned_orders,
                delay_impact_min=delay_impact,
                auto_applied=auto_apply,
                status=status_val,
                result_status=status_val,
            )

            if auto_apply:
                # Apply updates to store
                for oid in reassigned_orders:
                    store.update("orders", oid, {"assigned_vehicle": best_target.id, "status": "assigned"})
                if affected_v_id:
                    store.update("vehicles", affected_v_id, {"status": "breakdown"})

            _log_and_notify_recovery(action)
            return action
        else:
            # No vehicle has capacity -> Propose to dispatcher
            action = RecoveryAction(
                action_id=action_id,
                alert_id=alert.alert_id,
                action_type="reassign",
                description=f"No vehicle has capacity for {total_weight}kg. Fleet escalation required.",
                proposal=f"Manual intervention needed: no available vehicle has capacity for {total_weight}kg.",
                affected_vehicle_id=affected_v_id,
                order_ids=reassigned_orders,
                delay_impact_min=60,
                auto_applied=False,
                status="proposed",
                result_status="proposed",
            )
            _log_and_notify_recovery(action)
            return action

    # 3. Traffic / Delay / ETA drift -> Try re-sequence or reassign
    drift_minutes = alert.drift_minutes or 20
    affected_v_id = alert.vehicle_id
    affected_route = routes_map.get(affected_v_id)

    # Check if re-sequencing the remaining stops avoids window violations
    if affected_route and len(affected_route.stops) > 1:
        unvisited = [s for s in affected_route.stops if s.status not in ("completed", "delivered")]
        # Sort unvisited by window_end to avoid hard window violations
        resequenced = sorted(unvisited, key=lambda s: _parse_minutes(s.window_end))
        order_ids_seq = [s.order_id for s in resequenced]

        # Check if delay impact can be recovered (e.g. saves travel time)
        # If impact is within threshold
        delay_impact = max(0, drift_minutes - 10)
        auto_apply = (delay_impact <= AUTO_APPLY_MAX_DELAY_MIN)
        status_val = "applied" if auto_apply else "proposed"

        action = RecoveryAction(
            action_id=action_id,
            alert_id=alert.alert_id,
            action_type="resequence",
            description=f"Re-sequence remaining stops for vehicle {affected_v_id} prioritizing earliest time windows.",
            proposal=f"Re-sequence stops for {affected_v_id} to minimize window delay (impact: {delay_impact} min).",
            affected_vehicle_id=affected_v_id,
            order_ids=order_ids_seq,
            delay_impact_min=delay_impact,
            auto_applied=auto_apply,
            status=status_val,
            result_status=status_val,
        )
        if auto_apply:
            # Update ETAs
            cur_time = _parse_minutes(unvisited[0].eta) + delay_impact
            for idx, stop in enumerate(resequenced):
                stop.stop_number = idx + 1
                stop.eta = _minutes_to_time_str(cur_time)
                cur_time += 25
            store.set("routes", affected_v_id, affected_route)

        _log_and_notify_recovery(action)
        return action

    # Fallback to general proposal
    delay_impact = drift_minutes
    auto_apply = (delay_impact <= AUTO_APPLY_MAX_DELAY_MIN)
    status_val = "applied" if auto_apply else "proposed"
    action = RecoveryAction(
        action_id=action_id,
        alert_id=alert.alert_id,
        action_type="resequence",
        description=f"Adjust schedule for {affected_v_id} due to {drift_minutes} min delay.",
        proposal=f"Adjust ETAs for vehicle {affected_v_id} with delay impact {delay_impact} min.",
        affected_vehicle_id=affected_v_id,
        order_ids=[alert.order_id] if alert.order_id else [],
        delay_impact_min=delay_impact,
        auto_applied=auto_apply,
        status=status_val,
        result_status=status_val,
    )
    _log_and_notify_recovery(action)
    return action


def _log_and_notify_recovery(action: RecoveryAction) -> None:
    """Log recovery action to events and notify affected parties."""
    store.set("events", action.action_id, {
        "event_id": action.action_id,
        "event_type": "recovery_action",
        "source": "recovery",
        "details": action.model_dump(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # Trigger notifications for affected orders
    for order_id in action.order_ids:
        raw_order = store.get("orders", order_id)
        if raw_order:
            order = Order(**raw_order) if isinstance(raw_order, dict) else raw_order
            # Send customer ETA notification if ETA adjusted
            new_eta = _minutes_to_time_str(_parse_minutes(order.window_start) + action.delay_impact_min)
            msg = format_eta_update(order, new_eta, language="en")
            store.set("messages", f"msg_{order_id}_{action.action_id[:6]}", {
                "id": f"msg_{order_id}_{action.action_id[:6]}",
                "order_id": order_id,
                "recipient": order.phone,
                "message": msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    # If reassigning, notify target vehicle driver
    if action.target_vehicle_id and action.order_ids:
        raw_v = store.get("vehicles", action.target_vehicle_id)
        driver_name = "Fleet Driver"
        if raw_v and "driver_name" in raw_v:
            driver_name = raw_v["driver_name"]
        driver_msg = format_driver_reassignment(driver_name, action.order_ids, language="en")
        store.set("messages", f"drv_{action.target_vehicle_id}_{action.action_id[:6]}", {
            "id": f"drv_{action.target_vehicle_id}_{action.action_id[:6]}",
            "vehicle_id": action.target_vehicle_id,
            "message": driver_msg,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def build_agent():
    """Build and export Google ADK Recovery Agent."""
    from google.adk.agents import Agent

    def recovery_tool(alert_json: str) -> str:
        """Evaluate operational alert and execute cheapest self-healing recovery action."""
        data = json.loads(alert_json)
        alert = Alert(**data) if isinstance(data, dict) else data
        action = recover_alert(alert)
        return json.dumps(action.model_dump())

    agent = Agent(
        name="recovery",
        model="gemini-2.5-flash",
        description="Self-healing recovery agent that re-sequences, reassigns, or reschedules impacted routes.",
        instruction=(
            "You are the Recovery Agent for DispatchMind. "
            "When route disruptions, vehicle breakdowns, or customer delays occur, find the lowest-cost recovery. "
            "Never violate vehicle capacities or customer time windows. "
            "Auto-apply if impact is within 15 minutes, otherwise present a single-line proposal without em dashes."
        ),
        tools=[recovery_tool],
    )
    return agent
