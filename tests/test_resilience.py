"""Unit tests for the resilience layer and retry/fallback mechanics."""

import asyncio
from pathlib import Path
import pytest
from core.models import Degraded
from core.resilience import escalate_to_human, resilient
from core.store import JSONStore


@pytest.fixture
def temp_store(tmp_path: Path):
    """Fixture providing an isolated JSON store for event testing."""
    return JSONStore(base_dir=tmp_path / "resilience_store")


def test_flaky_function_succeeds_after_two_failures(temp_store: JSONStore):
    """Verify flaky function succeeds after 2 failures within retry budget."""
    attempts = 0

    @resilient(retries=3, base_delay=0.001, store=temp_store)
    def flaky_service() -> str:
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise ConnectionError(f"Transient error on attempt {attempts}")
        return "success_after_retry"

    result = flaky_service()
    assert result == "success_after_retry"
    assert attempts == 3
    # No fail events logged because it eventually succeeded
    fail_events = temp_store.list("events", filters={"event_type": "call_failed"})
    assert len(fail_events) == 0


def test_permanent_failure_triggers_fallback_and_logs_event(temp_store: JSONStore):
    """Verify permanent failure triggers fallback, returns Degraded, and logs event."""
    call_count = 0

    def mock_fallback(param: str) -> str:
        return f"fallback_value_for_{param}"

    @resilient(fallback=mock_fallback, retries=2, base_delay=0.001, store=temp_store)
    def broken_service(param: str) -> str:
        nonlocal call_count
        call_count += 1
        raise TimeoutError("Third party service unavailable")

    result = broken_service("route_matrix")

    assert call_count == 3  # initial attempt + 2 retries
    assert isinstance(result, Degraded)
    assert result.is_degraded is True
    assert result.fallback_result == "fallback_value_for_route_matrix"
    assert "broken_service failed after 2 retries" in result.reason
    assert "Third party service unavailable" in (result.error or "")

    # Check that event was logged to the events collection
    events = temp_store.list("events")
    assert len(events) >= 1
    fail_event = next(e for e in events if e.get("event_type") == "call_failed")
    assert fail_event["source"] == "broken_service"
    assert fail_event["details"]["retries"] == 2


def test_escalation_event_appears_in_store(temp_store: JSONStore):
    """Verify escalate_to_human and escalate=True records needs_human event."""
    # Direct escalation call
    event = escalate_to_human(
        source="driver_monitor",
        reason="Driver vehicle TN09-AB-1234 motionless for 45 minutes",
        details={"vehicle_id": "TN09-AB-1234", "idle_minutes": 45},
        store=temp_store,
    )
    assert event.event_type == "needs_human"
    assert event.source == "driver_monitor"

    human_events = temp_store.list("events", filters={"event_type": "needs_human"})
    assert len(human_events) == 1
    assert human_events[0]["details"]["vehicle_id"] == "TN09-AB-1234"

    # Escalation via resilient decorator
    @resilient(retries=1, escalate=True, base_delay=0.001, store=temp_store)
    def critical_api():
        raise RuntimeError("Fatal database crash")

    degraded = critical_api()
    assert isinstance(degraded, Degraded)

    all_human_events = temp_store.list("events", filters={"event_type": "needs_human"})
    assert len(all_human_events) == 2


def test_async_resilient_decorator(temp_store: JSONStore):
    """Verify resilient decorator on async coroutines."""
    attempts = 0

    @resilient(retries=2, base_delay=0.001, store=temp_store)
    async def async_flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ValueError("Async network glitch")
        return "async_ok"

    res = asyncio.run(async_flaky())
    assert res == "async_ok"
    assert attempts == 2
