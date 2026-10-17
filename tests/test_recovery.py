"""Tests for Monitor and Recovery agents (Phase P5)."""

import json
import pytest
from pathlib import Path

from core.models import Alert, RecoveryAction, Order, Vehicle, VehicleRoute, Stop
from core.store import store
from agents.monitor import check_active_routes, build_agent as build_monitor_agent
from agents.recovery import recover_alert, build_agent as build_recovery_agent


@pytest.fixture(autouse=True)
def setup_store():
    """Clear store collections before each test."""
    store.clear()
    yield
    store.clear()


def test_monitor_eta_drift_detection():
    """Test that stop with live ETA drift > 15 minutes triggers an ETA_DRIFT alert."""
    stop = Stop(
        stop_number=1,
        order_id="ORD-101",
        customer_name="Test Customer",
        lat=13.0418,
        lng=80.2341,
        weight_kg=25.0,
        planned_eta="10:00",
        eta="10:30",  # 30 min drift > 15 min threshold
        window_start="09:00",
        window_end="12:00",
        status="in_transit",
    )
    route = VehicleRoute(
        vehicle_id="TN-09-AB-1234",
        stops=[stop],
        total_km=15.0,
        total_weight_kg=25.0,
    )

    alerts = check_active_routes(routes=[route])
    assert len(alerts) >= 1
    drift_alert = next((a for a in alerts if a.alert_type == "ETA_DRIFT"), None)
    assert drift_alert is not None
    assert drift_alert.drift_minutes == 30
    assert drift_alert.order_id == "ORD-101"
    assert drift_alert.vehicle_id == "TN-09-AB-1234"


def test_monitor_idle_driver_detection():
    """Test that vehicle idle > 20 minutes triggers DRIVER_IDLE alert."""
    vehicles = [
        {"id": "TN-09-AB-1234", "status": "on_route", "idle_minutes": 25},
        {"id": "TN-01-CD-5678", "status": "on_route", "idle_minutes": 5},
    ]
    alerts = check_active_routes(routes=[], vehicles_state=vehicles)
    idle_alerts = [a for a in alerts if a.alert_type == "DRIVER_IDLE"]
    assert len(idle_alerts) == 1
    assert idle_alerts[0].vehicle_id == "TN-09-AB-1234"
    assert idle_alerts[0].idle_minutes == 25


def test_breakdown_injection_leads_to_reassignment():
    """Test breakdown alert reassigns stops to nearest vehicle with available capacity."""
    # Seed 2 vehicles
    v1 = Vehicle(id="V1", model="Ace", capacity_kg=500.0, current_lat=13.01, current_lng=80.20, status="breakdown")
    v2 = Vehicle(id="V2", model="Dost", capacity_kg=1000.0, current_lat=13.02, current_lng=80.21, status="available")
    store.set("vehicles", v1.id, v1)
    store.set("vehicles", v2.id, v2)

    # Order on broken-down vehicle
    order = Order(
        id="ORD-BD-1",
        customer_name="Factory A",
        phone="9840112233",
        address="Guindy",
        pincode="600032",
        weight_kg=150.0,
        lat=13.01,
        lng=80.20,
    )
    store.set("orders", order.id, order)

    stop = Stop(
        stop_number=1,
        order_id="ORD-BD-1",
        lat=13.01,
        lng=80.20,
        weight_kg=150.0,
        eta="11:00",
        window_start="10:00",
        window_end="13:00",
        status="in_transit",
    )
    r1 = VehicleRoute(vehicle_id="V1", stops=[stop], total_weight_kg=150.0)
    store.set("routes", "V1", r1)

    alert = Alert(
        alert_id="ALT-BREAKDOWN-1",
        vehicle_id="V1",
        order_id="ORD-BD-1",
        alert_type="breakdown",
        severity="critical",
        message="Vehicle V1 engine breakdown on GST Road",
    )

    action = recover_alert(alert=alert, vehicles=[v1, v2], routes=[r1], orders=[order])
    assert action.action_type == "reassign"
    assert action.target_vehicle_id == "V2"
    assert "ORD-BD-1" in action.order_ids
    # Events must be logged
    logged_event = store.get("events", action.action_id)
    assert logged_event is not None
    assert logged_event["event_type"] == "recovery_action"


def test_traffic_delay_leads_to_resequencing():
    """Test traffic delay alert leads to re-sequencing of stops."""
    v = Vehicle(id="V1", model="Ace", capacity_kg=500.0, current_lat=13.01, current_lng=80.20, status="on_route")
    s1 = Stop(stop_number=1, order_id="ORD-A", lat=13.02, lng=80.21, weight_kg=50.0, eta="11:30", window_start="09:00", window_end="14:00")
    s2 = Stop(stop_number=2, order_id="ORD-B", lat=13.03, lng=80.22, weight_kg=50.0, eta="12:00", window_start="09:00", window_end="12:30")
    route = VehicleRoute(vehicle_id="V1", stops=[s1, s2], total_weight_kg=100.0)

    alert = Alert(
        alert_id="ALT-TRAFFIC-1",
        vehicle_id="V1",
        order_id="ORD-A",
        alert_type="ETA_DRIFT",
        severity="WARNING",
        drift_minutes=25,
        message="Heavy traffic congestion on Anna Salai",
    )

    action = recover_alert(alert=alert, vehicles=[v], routes=[route], orders=[])
    assert action.action_type == "resequence"
    assert action.affected_vehicle_id == "V1"
    # S2 had earlier window_end (12:30 < 14:00), so resequence should prioritize S2
    assert action.order_ids == ["ORD-B", "ORD-A"]


def test_wrong_address_leads_to_reschedule():
    """Test wrong address or unreachable customer leads to reschedule action."""
    order = Order(
        id="ORD-WRONG-1",
        customer_name="John Doe",
        phone="9840112233",
        address="Non-existent street 99",
        pincode="600001",
        weight_kg=20.0,
    )
    store.set("orders", order.id, order)

    alert = Alert(
        alert_id="ALT-ADDR-1",
        vehicle_id="V1",
        order_id="ORD-WRONG-1",
        alert_type="wrong_address",
        severity="medium",
        message="Customer address not found and phone unreachable",
    )

    action = recover_alert(alert=alert, orders=[order])
    assert action.action_type == "reschedule"
    assert action.auto_applied is True
    assert action.status == "applied"
    updated_order = store.get("orders", "ORD-WRONG-1")
    assert updated_order["status"] == "rescheduled"


def test_capacity_constraints_respected_during_recovery():
    """Test that recovery will NOT assign orders to vehicle exceeding capacity."""
    v_small = Vehicle(id="V_SMALL", model="Ace", capacity_kg=100.0, current_lat=13.01, current_lng=80.20, status="available")
    # Order exceeds capacity
    heavy_order = Order(
        id="ORD-HEAVY",
        customer_name="Heavy Co",
        phone="9840112233",
        address="Central Hub",
        pincode="600001",
        weight_kg=250.0,
    )
    store.set("orders", heavy_order.id, heavy_order)

    alert = Alert(
        alert_id="ALT-HEAVY-1",
        vehicle_id="V_BROKEN",
        order_id="ORD-HEAVY",
        alert_type="breakdown",
        severity="critical",
        message="Vehicle broken down with 250kg package",
    )

    action = recover_alert(alert=alert, vehicles=[v_small], routes=[], orders=[heavy_order])
    # Cannot auto-apply or assign to V_SMALL because 250 > 100
    assert action.auto_applied is False
    assert action.status == "proposed"
    assert action.target_vehicle_id is None


def test_build_agents_adk():
    """Verify ADK agents build correctly."""
    m_agent = build_monitor_agent()
    assert m_agent.name == "monitor"
    r_agent = build_recovery_agent()
    assert r_agent.name == "recovery"
