"""Tests for Comms and POD agents (Phase P6)."""

import pytest
from pathlib import Path

from core.models import Order, PODResult
from core.store import store
from agents.comms import format_eta_update, format_driver_reassignment, generate_dispatcher_reply, build_agent as build_comms_agent
from agents.pod import process_pod, build_agent as build_pod_agent


@pytest.fixture(autouse=True)
def setup_store():
    """Clear store collections before each test."""
    store.clear()
    yield
    store.clear()


def test_comms_multi_lingual_eta_updates():
    """Test ETA updates in English, Hindi, and Tamil without em dashes."""
    order = Order(
        id="ORD-201",
        customer_name="Ramesh Kumar",
        phone="9840112233",
        address="10 Mount Road, Chennai",
        pincode="600002",
        weight_kg=15.0,
    )

    en_msg = format_eta_update(order, "14:30", language="en")
    assert "14:30" in en_msg
    assert "ORD-201" in en_msg
    assert "—" not in en_msg

    hi_msg = format_eta_update(order, "14:30", language="hi")
    assert "14:30" in hi_msg
    assert "ORD-201" in hi_msg
    assert "डिस्पैचमाइंड" in hi_msg
    assert "—" not in hi_msg

    ta_msg = format_eta_update(order, "14:30", language="ta")
    assert "14:30" in ta_msg
    assert "ORD-201" in ta_msg
    assert "டிஸ்பாட்ச்மைண்ட்" in ta_msg
    assert "—" not in ta_msg


def test_comms_driver_reassignment_and_dispatcher_reply():
    """Test driver notification and dispatcher conversational reply."""
    driver_msg = format_driver_reassignment("Murugan", ["ORD-1", "ORD-2"], language="en")
    assert "Murugan" in driver_msg
    assert "2" in driver_msg
    assert "—" not in driver_msg

    reply = generate_dispatcher_reply(
        "fleet status overview",
        state_summary={"active_vehicles": 4, "pending_orders": 8, "alerts_count": 1},
        language="en",
    )
    assert "4 active vehicles" in reply
    assert "8 pending orders" in reply
    assert "—" not in reply


def test_pod_valid_delivery_photo_closes_order():
    """Test valid delivery photo verifies POD and closes the order with DELIVERED status."""
    order = Order(
        id="ORD-POD-001",
        customer_name="Lakshmi Narayanan",
        phone="9840556677",
        address="34 Pondy Bazaar, T. Nagar",
        pincode="600017",
        weight_kg=12.0,
        status="in_transit",
    )
    store.set("orders", order.id, order)

    # Valid photo input
    dummy_photo_bytes = b"EXIF_HEADER_PARCEL_DELIVERED_DOORSTEP_VALID_IMAGE_DATA_1234567890"
    res = process_pod(order_id="ORD-POD-001", photo_input=dummy_photo_bytes, save_to_store=True)

    assert isinstance(res, PODResult)
    assert res.verified is True
    assert res.confidence >= 0.7
    assert res.needs_human is False
    assert res.recipient_name is not None

    # Check store order status
    updated_order = store.get("orders", "ORD-POD-001")
    assert updated_order["status"] == "delivered"
    assert updated_order["pod_id"] == res.pod_id

    # Check event logged
    event = store.get("events", f"evt_{res.pod_id[:8]}")
    assert event is not None
    assert event["event_type"] == "order_delivered"


def test_pod_blank_invalid_photo_flags_low_confidence_and_escalates():
    """Test blank/invalid photo flags low confidence and logs needs_human escalation event."""
    order = Order(
        id="ORD-POD-002",
        customer_name="Priya Raman",
        phone="9840998877",
        address="12 Cathedral Road",
        pincode="600086",
        weight_kg=5.0,
        status="in_transit",
    )
    store.set("orders", order.id, order)

    # Blank photo bytes
    blank_bytes = b"BLANK_IMAGE_CORRUPTED_OR_EMPTY_00000000000000000"
    res = process_pod(order_id="ORD-POD-002", photo_input=blank_bytes, save_to_store=True)

    assert isinstance(res, PODResult)
    assert res.verified is False
    assert res.confidence < 0.7
    assert res.needs_human is True

    # Order must NOT be marked delivered
    order_in_store = store.get("orders", "ORD-POD-002")
    assert order_in_store["status"] == "in_transit"

    # Escalation event must be present in store
    events = store.list("events", filters={"event_type": "needs_human"})
    assert len(events) >= 1
    escalated = next((e for e in events if e.get("details", {}).get("order_id") == "ORD-POD-002"), None)
    assert escalated is not None
    assert escalated["source"] == "pod"


def test_build_agents_adk():
    """Verify ADK agents build correctly."""
    c_agent = build_comms_agent()
    assert c_agent.name == "comms"
    p_agent = build_pod_agent()
    assert p_agent.name == "pod"
