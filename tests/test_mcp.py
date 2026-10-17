"""Unit tests for DispatchMind FastMCP servers.

Covers:
- Standalone startup and tool registration for all 5 MCP servers.
- Resilient fallback execution without network credentials (DEMO_MODE=true).
- Store operations through OrdersServer.
- MapsServer geocoding, distance matrix, and ETA calculation with haversine.
- WeatherServer forecast and rain risk assessment.
- NotifyServer messaging and demo fallback.
- DocsServer local storage and retrieval.
"""

import base64
from pathlib import Path
import pytest

from core.models import Event, Order, Degraded
from core.store import get_store
from mcp_servers.docs_server import (
    fallback_get_file,
    fallback_save_file,
    get_file,
    mcp as docs_mcp,
    save_file,
)
from mcp_servers.maps_server import (
    distance_matrix,
    eta_between,
    fallback_distance_matrix,
    fallback_eta_between,
    fallback_geocode,
    geocode,
    haversine_distance,
    mcp as maps_mcp,
    road_distance_km,
)
from mcp_servers.notify_server import (
    fallback_send_message,
    mcp as notify_mcp,
    send_message,
)
from mcp_servers.orders_server import (
    assign_order,
    create_order,
    get_order,
    list_orders,
    list_vehicles,
    log_event,
    mcp as orders_mcp,
    update_order,
)
from mcp_servers.weather_server import (
    fallback_forecast_for_point,
    fallback_rain_risk,
    forecast_for_point,
    mcp as weather_mcp,
    rain_risk,
)


@pytest.mark.anyio
async def test_all_five_mcp_servers_register_expected_tools():
    """Verify that all 5 FastMCP servers register their full tool rosters."""
    servers_and_tools = [
        (
            orders_mcp,
            [
                "list_orders",
                "get_order",
                "create_order",
                "update_order",
                "assign_order",
                "list_vehicles",
                "log_event",
            ],
        ),
        (maps_mcp, ["geocode", "distance_matrix", "eta_between"]),
        (weather_mcp, ["forecast_for_point", "rain_risk"]),
        (notify_mcp, ["send_message"]),
        (docs_mcp, ["save_file", "get_file"]),
    ]

    for server, expected_tools in servers_and_tools:
        registered = await server.list_tools()
        registered_names = {t.name for t in registered}
        for expected in expected_tools:
            assert expected in registered_names, (
                f"Tool {expected} not found on server {server.name}"
            )


# ==============================================================================
# OrdersServer Tests
# ==============================================================================

def test_orders_server_crud_and_assignment():
    """Verify order creation, listing, updating, and vehicle assignment."""
    order_payload = {
        "id": "ORD-MCP-001",
        "customer_name": "T. Nagar Textile Mart",
        "phone": "9840199999",
        "address": "45 South Usman Road, T. Nagar, Chennai",
        "pincode": "600017",
        "weight_kg": 25.5,
        "window_start": "10:00",
        "window_end": "13:00",
    }

    created = create_order(order_payload)
    assert created["id"] == "ORD-MCP-001"
    assert created["status"] == "pending"
    assert created["weight_kg"] == 25.5

    fetched = get_order("ORD-MCP-001")
    assert fetched is not None
    assert fetched["customer_name"] == "T. Nagar Textile Mart"

    # List orders with status filter
    pending_orders = list_orders(status="pending")
    assert any(o["id"] == "ORD-MCP-001" for o in pending_orders)

    # Update order
    updated = update_order("ORD-MCP-001", {"weight_kg": 30.0})
    assert updated["weight_kg"] == 30.0

    # Assign order to vehicle
    assigned = assign_order("ORD-MCP-001", "TN09AB1234")
    assert assigned["assigned_vehicle"] == "TN09AB1234"
    assert assigned["status"] == "assigned"


def test_orders_server_list_vehicles():
    """Verify vehicles listing through orders server."""
    vehicles = list_vehicles()
    assert isinstance(vehicles, list)


def test_orders_server_log_event():
    """Verify logging operational and audit events."""
    evt = log_event(
        source="mcp_test",
        event_type="dispatch_plan",
        status="success",
        message="Route plan generated successfully",
        metadata={"total_orders": 12, "routes": 4},
    )
    assert evt["event_type"] == "dispatch_plan"
    assert evt["source"] == "mcp_test"
    assert evt["status"] == "success"
    assert "evt_" in evt["event_id"]


# ==============================================================================
# MapsServer Tests
# ==============================================================================

def test_haversine_and_road_distance_calculation():
    """Verify haversine distance and 1.4 road factor multiplier."""
    # Guindy (13.0067, 80.2025) to T. Nagar (13.0418, 80.2341)
    straight_km = haversine_distance(13.0067, 80.2025, 13.0418, 80.2341)
    road_km = road_distance_km(13.0067, 80.2025, 13.0418, 80.2341, road_factor=1.4)

    assert 4.0 <= straight_km <= 7.0
    assert road_km > straight_km
    assert round(road_km, 2) == round(straight_km * 1.4, 2)


def test_maps_server_geocode_fallback():
    """Verify offline fallback geocoding for pincodes and localities."""
    res_pin = geocode("Chennai shipment to 600017")
    assert res_pin["lat"] == 13.0418
    assert res_pin["lng"] == 80.2341
    assert "600017" in res_pin["formatted_address"]

    res_loc = geocode("Deliver near Adyar Signal")
    assert res_loc["lat"] == 13.0012
    assert res_loc["lng"] == 80.2565
    assert "Adyar" in res_loc["formatted_address"]

    res_unknown = geocode("Unknown Faraway Area")
    assert res_unknown["lat"] is not None
    assert res_unknown["lng"] is not None


def test_maps_server_distance_matrix_and_eta():
    """Verify distance matrix and pairwise ETA calculation."""
    origins = [{"lat": 13.0067, "lng": 80.2025}]  # Guindy
    destinations = [
        {"lat": 13.0418, "lng": 80.2341},  # T. Nagar
        {"lat": 13.0012, "lng": 80.2565},  # Adyar
    ]

    mat = distance_matrix(origins=origins, destinations=destinations)
    assert "distances_km" in mat
    assert "durations_min" in mat
    assert len(mat["distances_km"]) == 1
    assert len(mat["distances_km"][0]) == 2
    assert mat["distances_km"][0][0] > 0
    assert mat["durations_min"][0][0] > 0

    eta_res = eta_between(13.0067, 80.2025, 13.0418, 80.2341)
    assert eta_res["km"] > 0
    assert eta_res["eta_minutes"] > 0


# ==============================================================================
# WeatherServer Tests
# ==============================================================================

def test_weather_server_forecast_and_rain_risk():
    """Verify weather forecasting and rain risk detection."""
    # Chennai coordinates
    lat, lng = 13.0827, 80.2707
    res = forecast_for_point(lat=lat, lng=lng)
    forecast = res.fallback_result if isinstance(res, Degraded) else res

    assert "temperature_c" in forecast
    assert "condition" in forecast
    assert forecast["latitude"] is not None

    res_risk = rain_risk(lat=lat, lng=lng, window_hours=3)
    risk = res_risk.fallback_result if isinstance(res_risk, Degraded) else res_risk
    assert "rain_probability" in risk
    assert "has_risk" in risk
    assert isinstance(risk["has_risk"], bool)
    assert risk["warning_level"] in ["none", "low", "moderate", "high"]


def test_weather_fallback_simulation():
    """Verify deterministic simulated weather fallback."""
    fb = fallback_forecast_for_point(13.04, 80.23)
    assert fb["source"] == "simulated_fallback"
    assert fb["temperature_c"] == 31.5

    fb_risk = fallback_rain_risk(13.04, 80.23, window_hours=4)
    assert fb_risk["has_risk"] is False
    assert fb_risk["source"] == "simulated_fallback"


# ==============================================================================
# NotifyServer Tests
# ==============================================================================

def test_notify_server_send_message():
    """Verify notification sending and store.messages recording."""
    res = send_message(
        channel="sms",
        chat_id="9840112233",
        text="Your delivery ORD-101 will arrive at 10:45 AM.",
    )
    assert res["status"] == "sent"
    assert res["channel"] == "sms"
    assert "msg_" in res["message_id"]

    # Verify message is persisted to the store
    store = get_store()
    stored_msg = store.get("messages", res["message_id"])
    assert stored_msg is not None
    assert stored_msg["text"] == "Your delivery ORD-101 will arrive at 10:45 AM."
    assert stored_msg["chat_id"] == "9840112233"


# ==============================================================================
# DocsServer Tests
# ==============================================================================

def test_docs_server_save_and_get_file(tmp_path: Path):
    """Verify document saving and retrieval via base64."""
    test_content = b"DispatchMind sample invoice invoice_001 Chennai Hub"
    b64_content = base64.b64encode(test_content).decode("utf-8")

    save_res = save_file(
        filename="invoice_001.pdf",
        content_base64=b64_content,
        category="invoice",
    )

    assert "file_id" in save_res
    assert save_res["filename"] == "invoice_001.pdf"
    assert save_res["size_bytes"] == len(test_content)
    assert Path(save_res["path"]).exists()

    # Retrieve by file_id
    get_res = get_file(save_res["file_id"])
    assert get_res["size_bytes"] == len(test_content)
    decoded = base64.b64decode(get_res["content_base64"])
    assert decoded == test_content
