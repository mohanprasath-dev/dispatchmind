"""Database seed script for demo and local development."""

import json
import logging
from pathlib import Path
from typing import Optional

from core.config import BASE_DIR
from core.models import Driver, Order, Vehicle
from core.store import BaseStore, get_store

logger = logging.getLogger(__name__)

DEFAULT_SEED_FILE = BASE_DIR / "data" / "seed.json"


def seed_store(
    store: Optional[BaseStore] = None,
    seed_file: Optional[Path] = None,
) -> dict[str, int]:
    """Seed the database with initial orders, vehicles, and drivers."""
    target_store = store or get_store()
    seed_path = seed_file or DEFAULT_SEED_FILE

    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file not found at {seed_path}")

    with open(seed_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    orders_data = data.get("orders", [])
    vehicles_data = data.get("vehicles", [])
    drivers_data = data.get("drivers", [])

    counts = {"orders": 0, "vehicles": 0, "drivers": 0, "events": 0}

    for order_dict in orders_data:
        order = Order(**order_dict)
        target_store.set("orders", order.id, order)
        counts["orders"] += 1

    for vehicle_dict in vehicles_data:
        vehicle = Vehicle(**vehicle_dict)
        target_store.set("vehicles", vehicle.id, vehicle)
        counts["vehicles"] += 1

    for driver_dict in drivers_data:
        driver = Driver(**driver_dict)
        target_store.set("drivers", driver.id, driver)
        counts["drivers"] += 1

    # Seed historical delivery completion events for feedback loop
    from core.feedback import get_default_historical_events

    events_data = data.get("events") or get_default_historical_events()
    for evt_dict in events_data:
        evt_id = evt_dict.get("event_id") or f"evt_{counts['events']}"
        target_store.set("events", evt_id, evt_dict)
        counts["events"] += 1

    logger.info(
        "Seeding complete: %d orders, %d vehicles, %d drivers, %d events",
        counts["orders"],
        counts["vehicles"],
        counts["drivers"],
        counts["events"],
    )
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Populating DispatchMind store...")
    result = seed_store()
    print(
        f"Seeded successfully: {result['orders']} orders, "
        f"{result['vehicles']} vehicles, {result['drivers']} drivers."
    )
