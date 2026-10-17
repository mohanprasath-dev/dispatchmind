"""Unit tests for the unified store interface and JSONStore fallback."""

import shutil
from pathlib import Path
import pytest
from core.models import Driver, Order, Vehicle
from core.store import JSONStore, get_store


@pytest.fixture
def temp_store(tmp_path: Path):
    """Fixture providing an isolated JSON store in a temp directory."""
    store_dir = tmp_path / "test_store"
    store = JSONStore(base_dir=store_dir)
    yield store
    if store_dir.exists():
        shutil.rmtree(store_dir)


def test_store_order_crud(temp_store: JSONStore):
    """Verify create, read, update, delete for Order in JSONStore."""
    order = Order(
        id="ORD-TEST-1",
        customer_name="Test Customer",
        phone="9876543210",
        address="100 Anna Salai, Chennai",
        pincode="600002",
        weight_kg=25.5,
        window_start="09:00",
        window_end="12:00",
    )

    temp_store.set("orders", order.id, order)

    fetched = temp_store.get("orders", "ORD-TEST-1")
    assert fetched is not None
    assert fetched["id"] == "ORD-TEST-1"
    assert fetched["customer_name"] == "Test Customer"
    assert fetched["weight_kg"] == 25.5

    temp_store.update("orders", "ORD-TEST-1", {"status": "assigned", "assigned_vehicle": "TN09-AB-1234"})
    updated = temp_store.get("orders", "ORD-TEST-1")
    assert updated["status"] == "assigned"
    assert updated["assigned_vehicle"] == "TN09-AB-1234"

    deleted = temp_store.delete("orders", "ORD-TEST-1")
    assert deleted is True
    assert temp_store.get("orders", "ORD-TEST-1") is None


def test_store_list_and_filter(temp_store: JSONStore):
    """Verify listing and filtering functionality."""
    v1 = Vehicle(id="V1", model="Tata Ace", capacity_kg=750.0, status="idle")
    v2 = Vehicle(id="V2", model="Mahindra Bolero", capacity_kg=1000.0, status="active")
    v3 = Vehicle(id="V3", model="Tata Ace EV", capacity_kg=600.0, status="idle")

    temp_store.set("vehicles", v1.id, v1)
    temp_store.set("vehicles", v2.id, v2)
    temp_store.set("vehicles", v3.id, v3)

    all_vehicles = temp_store.list("vehicles")
    assert len(all_vehicles) == 3

    idle_vehicles = temp_store.list("vehicles", filters={"status": "idle"})
    assert len(idle_vehicles) == 2
    assert {v["id"] for v in idle_vehicles} == {"V1", "V3"}


def test_store_clear(temp_store: JSONStore):
    """Verify clearing a collection."""
    d1 = Driver(id="D1", name="Driver 1", phone="9999999991")
    temp_store.set("drivers", d1.id, d1)
    assert len(temp_store.list("drivers")) == 1

    temp_store.clear("drivers")
    assert len(temp_store.list("drivers")) == 0


def test_get_store_demo_mode(tmp_path: Path):
    """Verify get_store returns JSONStore when demo_mode is True."""
    store = get_store(demo_mode=True, base_dir=tmp_path / "factory_store")
    assert isinstance(store, JSONStore)
