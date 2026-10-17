"""Tests for Feedback Agent and Tuning Loop (Phase P7)."""

import json
from pathlib import Path
import pytest

from core.feedback import (
    compute_eta_variance,
    compute_metrics_summary,
    get_default_historical_events,
)
from core.models import Order, TuningUpdate, Vehicle
from core.store import JSONStore
from agents.feedback import build_agent, run_feedback_cycle
from agents.planner import solve_vrp, time_to_minutes


@pytest.fixture
def temp_store(tmp_path: Path):
    """Provide an isolated JSONStore instance in temporary directory."""
    store_dir = tmp_path / "test_feedback_store"
    s = JSONStore(base_dir=store_dir)
    yield s


@pytest.fixture
def seed_fleet_orders():
    """Load canonical orders and vehicles from seed.json."""
    seed_file = Path("data/seed.json")
    assert seed_file.exists(), "data/seed.json must exist"
    with open(seed_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    orders = [Order(**o) for o in data["orders"]]
    vehicles = [Vehicle(**v) for v in data["vehicles"]]
    return orders, vehicles


def test_feedback_variance_buffers_at_least_three_pincodes(temp_store: JSONStore):
    """Verify feedback calculation computes and updates buffers for at least 3 pincodes."""
    historical_events = get_default_historical_events()
    variance_res = compute_eta_variance(historical_events)

    buffers = variance_res["pincode_buffers"]
    assert len(buffers) >= 3, f"Expected at least 3 pincodes, got {len(buffers)}"

    # Check key Chennai delivery hubs
    for pin in ["600017", "600058", "600042"]:
        assert pin in buffers, f"Pincode {pin} must be present in calculated buffers"
        assert buffers[pin] > 0, f"Buffer for {pin} must be a positive integer"

    # Check that failure reasons are tagged
    by_pincode = variance_res["by_pincode"]
    assert "traffic congestion" in by_pincode["600017"]["failure_reasons"]
    assert "waterlogging" in by_pincode["600042"]["failure_reasons"]
    assert "freight vehicle congestion" in by_pincode["600058"]["failure_reasons"]

    # Check hour band grouping
    assert "09-12" in by_pincode["600017"]["hour_bands"]
    assert "12-15" in by_pincode["600017"]["hour_bands"]

    # Verify execution via run_feedback_cycle
    primary_update = run_feedback_cycle(store=temp_store)
    assert isinstance(primary_update, TuningUpdate)
    assert primary_update.pincode in buffers
    assert primary_update.eta_buffer_min > 0

    # Verify all 3 pincodes stored in tuning collection
    tuning_docs = temp_store.list("tuning")
    stored_pins = {d["pincode"] for d in tuning_docs}
    assert {"600017", "600058", "600042"}.issubset(stored_pins)


def test_planner_ingests_feedback_buffers_and_adjusts_etas(
    temp_store: JSONStore,
    seed_fleet_orders,
    monkeypatch,
):
    """Verify Planner agent ingests new buffers from tuning store and adjusts ETAs accordingly."""
    orders, vehicles = seed_fleet_orders

    # Monkeypatch store in planner and feedback agents to use isolated temp_store
    import agents.planner as planner_module
    import agents.feedback as feedback_module

    monkeypatch.setattr(planner_module, "store", temp_store)
    monkeypatch.setattr(feedback_module, "global_store", temp_store)

    # 1. Plan routes before any tuning buffer is set
    temp_store.clear("tuning")
    plan_before = solve_vrp(orders=orders, vehicles=vehicles)
    etas_before = {s.order_id: s.eta for r in plan_before.routes for s in r.stops}

    # 2. Run feedback cycle to apply learned buffers to temp_store
    tuning_update = run_feedback_cycle(store=temp_store)
    assert tuning_update is not None

    # Check buffers in store
    learned_buffers = planner_module.get_tuning_buffers()
    assert len(learned_buffers) >= 3
    assert learned_buffers.get("600017", 0) > 0

    # 3. Plan routes after tuning buffers are applied
    plan_after = solve_vrp(orders=orders, vehicles=vehicles)
    etas_after = {s.order_id: s.eta for r in plan_after.routes for s in r.stops}

    # ORD-101 is located in 600017 (T. Nagar) which receives a buffer
    assert "ORD-101" in etas_before
    assert "ORD-101" in etas_after

    eta_before_min = time_to_minutes(etas_before["ORD-101"])
    eta_after_min = time_to_minutes(etas_after["ORD-101"])

    # Arrival time at ORD-101 or subsequent stops must be delayed by the buffer
    assert eta_after_min >= eta_before_min, (
        f"ETA with buffer ({etas_after['ORD-101']}) should be at or after baseline ({etas_before['ORD-101']})"
    )


def test_before_vs_after_metric_reduction():
    """Verify before vs after error metric reduction calculation."""
    events = get_default_historical_events()
    variance_res = compute_eta_variance(events)

    metrics = compute_metrics_summary(events, variance_res)

    assert "before_mean_error_min" in metrics
    assert "after_mean_error_min" in metrics
    assert "error_reduction_pct" in metrics
    assert "sample_count" in metrics

    assert metrics["sample_count"] == 48
    # Baseline mean error should be around ~24.8 minutes
    assert 24.0 <= metrics["before_mean_error_min"] <= 26.0
    # After-buffer mean error should drop down to ~6.2 minutes
    assert 5.0 <= metrics["after_mean_error_min"] <= 7.0
    # Error reduction percentage should demonstrate ~75% improvement
    assert 70.0 <= metrics["error_reduction_pct"] <= 85.0


def test_feedback_proposals_never_auto_modify_files(temp_store: JSONStore):
    """Verify feedback proposals produce text proposals but never auto-modify or touch files on disk."""
    # Capture modification times of existing files
    tracked_dirs = [Path("core"), Path("agents"), Path("app")]
    tracked_files = [p for d in tracked_dirs for p in d.glob("*.py")]

    pre_mtimes = {f: f.stat().st_mtime_ns for f in tracked_files}

    # Execute feedback cycle
    result = run_feedback_cycle(store=temp_store)

    # 1. Must produce a proposed diff in text form
    assert result.suggested_prompt_diff is not None
    assert "--- a/prompts/planner_constraints.txt" in result.suggested_prompt_diff
    assert "+++ b/prompts/planner_constraints.txt" in result.suggested_prompt_diff
    assert "+Pincode" in result.suggested_prompt_diff

    # 2. Verify no tracked source files were modified
    for f in tracked_files:
        assert f.stat().st_mtime_ns == pre_mtimes[f], (
            f"File {f} was modified during feedback execution! Auto-modifying files is forbidden."
        )

    # 3. Verify that prompts directory was not touched or created with prompt files
    prompt_file = Path("prompts/planner_constraints.txt")
    assert not prompt_file.exists(), "Prompt file must not be created on disk by feedback cycle"


def test_adk_feedback_agent_build():
    """Verify build_agent exports an ADK Agent instance for feedback."""
    agent = build_agent()
    assert agent is not None
    assert agent.name == "feedback"
    assert agent.model == "gemini-2.5-flash"
    assert len(agent.tools) >= 1


def test_tuning_applied_event_emitted(temp_store: JSONStore):
    """Verify that TUNING_APPLIED event is emitted to store.events."""
    run_feedback_cycle(store=temp_store)

    events = temp_store.list("events", filters={"event_type": "TUNING_APPLIED"})
    assert len(events) >= 1

    event = events[0]
    assert event["source"] == "feedback"
    assert "details" in event
    assert "updated_pincodes" in event["details"]
    assert "metrics" in event["details"]
    assert "suggested_prompt_diff" in event["details"]
