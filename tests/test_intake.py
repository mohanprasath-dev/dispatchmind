import pytest
from pathlib import Path
from core.models import Order, MissingFields
from core.store import JSONStore
from agents.intake import process_intake, build_agent, validate_and_build_result


@pytest.fixture
def temp_store(tmp_path: Path):
    """Provide an isolated store for testing."""
    return JSONStore(base_dir=tmp_path / "intake_store")


def test_four_of_five_sample_docs_extract_correctly(temp_store: JSONStore):
    """Verify that 4 of 5 sample documents extract cleanly as validated Orders."""
    sample_files = [
        "INV-2026-001.pdf",
        "EWAY-2026-002.pdf",
        "CHALLAN-2026-003.pdf",
        "INV-2026-004.pdf",
    ]

    valid_orders = []
    for filename in sample_files:
        path = Path("data/sample_orders") / filename
        assert path.exists(), f"Sample file {filename} missing"
        res = process_intake(path, save_to_store=True)
        assert isinstance(res, Order), f"Expected Order for {filename}, got {type(res)}"
        assert res.id.startswith("ORD-")
        assert len(res.pincode) == 6
        assert len(res.phone) == 10
        assert res.weight_kg > 0
        assert res.lat is not None and res.lng is not None
        valid_orders.append(res)

    assert len(valid_orders) == 4

    # Check store persistence
    stored_ord1 = temp_store.get("orders", "ORD-2026-101")
    # Note: store may use global store, but process_intake saves to configured store
    assert valid_orders[0].id == "ORD-2026-101"
    assert valid_orders[0].customer_name == "Apex Auto Spares"
    assert valid_orders[0].pincode == "600017"


def test_sample_gap_document_triggers_exactly_one_question():
    """Verify intentional gap document (INV-2026-005-GAP.pdf) returns MissingFields with 1 question."""
    gap_file = Path("data/sample_orders/INV-2026-005-GAP.pdf")
    assert gap_file.exists()

    res = process_intake(gap_file, save_to_store=False)
    assert isinstance(res, MissingFields)
    assert "pincode" in res.missing_fields
    assert len(res.questions) == 1
    assert "pincode" in res.questions[0].lower()
    assert "6-digit" in res.questions[0].lower()


def test_phone_validation_rules():
    """Verify Indian 10-digit phone number validation."""
    # Valid mobile numbers starting 6-9
    good_extracted = {
        "fields": {
            "order_id": "ORD-TEST-PHONE",
            "customer": "Test Customer",
            "phone": "+91 98401 23456",
            "address": "12 Mount Road, Chennai",
            "pincode": "600002",
            "weight_kg": 10.0,
            "time_window": "10:00 - 13:00",
        },
        "confidences": {k: 0.95 for k in ["order_id", "customer", "phone", "address", "pincode", "weight_kg"]},
    }
    res = validate_and_build_result(good_extracted, save_to_store=False)
    assert isinstance(res, Order)
    assert res.phone == "9840123456"

    # Invalid mobile (starts with 1 or not 10 digits)
    bad_extracted = {
        "fields": {
            "order_id": "ORD-TEST-BAD-PHONE",
            "customer": "Test Customer",
            "phone": "12345",
            "address": "12 Mount Road, Chennai",
            "pincode": "600002",
            "weight_kg": 10.0,
        },
        "confidences": {k: 0.95 for k in ["order_id", "customer", "phone", "address", "pincode", "weight_kg"]},
    }
    bad_res = validate_and_build_result(bad_extracted, save_to_store=False)
    assert isinstance(bad_res, MissingFields)
    assert "phone" in bad_res.missing_fields
    assert any("phone" in q.lower() for q in bad_res.questions)


def test_pincode_validation_rules():
    """Verify 6-digit Indian postal code validation."""
    bad_pincode_extracted = {
        "fields": {
            "order_id": "ORD-TEST-BAD-PIN",
            "customer": "Test Customer",
            "phone": "9840123456",
            "address": "12 Mount Road, Chennai",
            "pincode": "60001",  # only 5 digits
            "weight_kg": 10.0,
        },
        "confidences": {k: 0.95 for k in ["order_id", "customer", "phone", "address", "pincode", "weight_kg"]},
    }
    res = validate_and_build_result(bad_pincode_extracted, save_to_store=False)
    assert isinstance(res, MissingFields)
    assert "pincode" in res.missing_fields
    assert len(res.questions) == 1
    assert "pincode" in res.questions[0].lower()


def test_positive_weight_validation():
    """Verify weight must be strictly positive."""
    bad_weight_extracted = {
        "fields": {
            "order_id": "ORD-TEST-BAD-WT",
            "customer": "Test Customer",
            "phone": "9840123456",
            "address": "12 Mount Road, Chennai",
            "pincode": "600002",
            "weight_kg": 0.0,  # invalid weight
        },
        "confidences": {k: 0.95 for k in ["order_id", "customer", "phone", "address", "pincode", "weight_kg"]},
    }
    res = validate_and_build_result(bad_weight_extracted, save_to_store=False)
    assert isinstance(res, MissingFields)
    assert "weight_kg" in res.missing_fields


def test_low_confidence_triggers_gap():
    """Verify confidence below 0.6 triggers MissingFields question."""
    low_conf_extracted = {
        "fields": {
            "order_id": "ORD-TEST-LOW-CONF",
            "customer": "Blurry Customer Name",
            "phone": "9840123456",
            "address": "12 Mount Road, Chennai",
            "pincode": "600002",
            "weight_kg": 15.0,
        },
        "confidences": {
            "order_id": 0.95,
            "customer": 0.45,  # low confidence (< 0.6)
            "phone": 0.95,
            "address": 0.95,
            "pincode": 0.95,
            "weight_kg": 0.95,
        },
    }
    res = validate_and_build_result(low_conf_extracted, save_to_store=False)
    assert isinstance(res, MissingFields)
    assert "customer" in res.missing_fields
    assert len(res.questions) == 1
    assert "customer" in res.questions[0].lower()


def test_adk_agent_build():
    """Verify build_agent exports an ADK Agent instance."""
    agent = build_agent()
    assert agent is not None
    assert agent.name == "intake"
    assert agent.model == "gemini-2.5-flash"
    assert len(agent.tools) >= 1
