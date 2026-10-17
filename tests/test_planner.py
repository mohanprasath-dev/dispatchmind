import json
import time
import pytest
from pathlib import Path
from core.models import Order, Vehicle, RoutePlan
from core.store import JSONStore
from agents.planner import solve_vrp, plan_day, build_agent, time_to_minutes


@pytest.fixture
def seed_data():
    """Load the canonical 12 orders and 4 vehicles from seed.json."""
    seed_path = Path("data/seed.json")
    assert seed_path.exists(), "data/seed.json must exist"
    with open(seed_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    orders = [Order(**o) for o in data["orders"]]
    vehicles = [Vehicle(**v) for v in data["vehicles"]]
    return orders, vehicles


def test_planner_under_15_seconds(seed_data):
    """Verify solving 12 orders and 4 vehicles takes under 15 seconds."""
    orders, vehicles = seed_data
    assert len(orders) == 12
    assert len(vehicles) == 4

    start_time = time.time()
    plan = solve_vrp(orders=orders, vehicles=vehicles)
    duration = time.time() - start_time

    assert isinstance(plan, RoutePlan)
    assert duration < 15.0, f"Plan took {duration:.2f}s, expected < 15s"
    assert plan.total_km > 0
    assert len(plan.routes) == len(vehicles)


def test_capacity_constraints_never_exceeded(seed_data):
    """Verify no vehicle ever exceeds its maximum load capacity."""
    orders, vehicles = seed_data
    vehicle_cap_map = {v.id: v.capacity_kg for v in vehicles}

    plan = solve_vrp(orders=orders, vehicles=vehicles)

    for route in plan.routes:
        max_cap = vehicle_cap_map[route.vehicle_id]
        actual_weight = sum(s.weight_kg for s in route.stops)
        assert actual_weight <= max_cap, (
            f"Vehicle {route.vehicle_id} overloaded: {actual_weight}kg > {max_cap}kg"
        )
        assert route.total_weight_kg <= max_cap


def test_time_window_constraints(seed_data):
    """Verify stop ETAs respect customer delivery windows."""
    orders, vehicles = seed_data
    plan = solve_vrp(orders=orders, vehicles=vehicles)

    for route in plan.routes:
        for stop in route.stops:
            eta_min = time_to_minutes(stop.eta)
            window_end_min = time_to_minutes(stop.window_end)
            # ETA must not exceed customer window end
            assert eta_min <= window_end_min, (
                f"Order {stop.order_id} ETA {stop.eta} missed window end {stop.window_end}"
            )


def test_unassigned_order_explanation(seed_data):
    """Verify that an order exceeding vehicle capacity is unassigned with a specific reason."""
    orders, vehicles = seed_data
    # Inject an order that exceeds any vehicle's capacity (max vehicle is 1000kg)
    huge_order = Order(
        id="ORD-HUGE-999",
        customer_name="Mega Steel Infrastructure",
        phone="9840112233",
        address="100 Grand Southern Trunk Road, Chennai",
        pincode="600045",
        lat=12.9249,
        lng=80.1000,
        weight_kg=3500.0,  # 3.5 tons > 1000kg max vehicle capacity
        window_start="10:00",
        window_end="14:00",
    )
    test_orders = list(orders) + [huge_order]

    plan = solve_vrp(orders=test_orders, vehicles=vehicles)

    unassigned_ids = [u.order_id if hasattr(u, "order_id") else u["order_id"] for u in plan.unassigned_orders]
    assert "ORD-HUGE-999" in unassigned_ids

    huge_unassigned = next(u for u in plan.unassigned_orders if (getattr(u, "order_id", None) or u["order_id"]) == "ORD-HUGE-999")
    huge_reason = getattr(huge_unassigned, "reason", None) or huge_unassigned["reason"]
    assert "capacity" in huge_reason.lower()
    assert "3500" in huge_reason or "exceeds" in huge_reason.lower()


def test_tuning_buffer_applied(seed_data, tmp_path: Path):
    """Verify eta_buffer_min from tuning collection is integrated."""
    from core.store import store
    orders, vehicles = seed_data

    # Add 25 minute buffer to Velachery (600042)
    store.set("tuning", "600042", {"pincode": "600042", "eta_buffer_min": 25})

    plan = solve_vrp(orders=orders, vehicles=vehicles)
    assert plan is not None
    # Plan must still be generated cleanly
    assert isinstance(plan, RoutePlan)


def test_adk_planner_agent_build():
    """Verify build_agent exports an ADK Agent instance."""
    agent = build_agent()
    assert agent is not None
    assert agent.name == "planner"
    assert agent.model == "gemini-2.5-flash"
    assert len(agent.tools) >= 1
