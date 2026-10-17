"""Feedback and continuous learning agent for DispatchMind.

Analyzes completed delivery events, computes ETA prediction variance grouped by
pincode and hour band, writes updated buffer recommendations to the tuning store,
tags recurrent delivery obstacles, and generates prompt / constraint diff proposals.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.config import GOOGLE_API_KEY
from core.feedback import (
    compute_eta_variance,
    compute_metrics_summary,
    get_default_historical_events,
)
from core.models import Event, TuningUpdate
from core.resilience import resilient
from core.store import BaseStore, get_store
from core.store import store as global_store

logger = logging.getLogger(__name__)


def generate_prompt_diff(
    pincode_buffers: Dict[str, int],
    by_pincode: Dict[str, Any],
) -> str:
    """
    Generate proposed prompt / parameter adjustments as a unified diff text proposal.
    NEVER writes or modifies files on disk.
    """
    diff_lines = [
        "--- a/prompts/planner_constraints.txt",
        "+++ b/prompts/planner_constraints.txt",
        "@@ -1,5 +1,8 @@",
        " [DispatchMind Dynamic Regional Buffers]",
    ]
    for pincode, buf in sorted(pincode_buffers.items()):
        pin_info = by_pincode.get(pincode, {})
        reasons = pin_info.get("failure_reasons", [])
        reason_str = f" ({', '.join(reasons[:2])})" if reasons else ""
        diff_lines.append(f"+Pincode {pincode}: Add +{buf} min buffer{reason_str}")

    return "\n".join(diff_lines)


def explain_tuning_with_gemini(summary_text: str) -> str:
    """Call Gemini 2.5 Flash to generate a plain English explanation of the feedback tuning cycle."""
    if not GOOGLE_API_KEY:
        return generate_deterministic_explanation(summary_text)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GOOGLE_API_KEY)
        prompt = (
            "You are the DispatchMind Continuous Learning Agent. "
            "Review the following delivery variance metrics and postal buffer updates:\n\n"
            f"{summary_text}\n\n"
            "Provide a concise summary explaining which postal codes experienced systematic delays, "
            "the root causes (traffic, road constraints, weather), and how the new ETA buffers "
            "will protect upcoming delivery schedules. "
            "Do not use em dashes in your response."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=500,
            ),
        )
        if response and response.text:
            import re
            return re.sub(r"[\u2013\u2014]", "-", response.text).strip()
    except Exception as exc:
        logger.warning(f"Gemini explanation failed, using fallback: {exc}")

    return generate_deterministic_explanation(summary_text)


def generate_deterministic_explanation(summary_text: str) -> str:
    """Clean fallback plain English explanation of the feedback tuning cycle."""
    return (
        "Feedback analysis completed across historical delivery logs. "
        "Systematic delivery delays identified and mitigated via calibrated postal buffers. "
        "Planner agent will incorporate updated buffers in subsequent routing runs."
    )


@resilient(retries=2, base_delay=0.01)
def run_feedback_cycle(store: Optional[BaseStore] = None) -> TuningUpdate:
    """
    Execute full feedback and learning cycle:
    1. Reads completed delivery events and route logs from store.events.
    2. Computes updated eta_buffer_min per pincode.
    3. Writes updated postal buffers to store.tuning collection (for Planner agent to read on next run).
    4. Tags recurrent failure reasons (e.g. traffic congestion, narrow roads, waterlogging).
    5. Proposes prompt or parameter diffs as text proposals (NEVER auto-edit prompts or code files).
    6. Emits TUNING_APPLIED event to store.events.
    7. Returns primary TuningUpdate instance.
    """
    target_store = store or global_store

    # 1. Read completed delivery events
    raw_events = target_store.list("events")
    delivery_events = [
        e for e in raw_events
        if e.get("event_type") in (
            "delivery_completed", "delivery", "POD_VERIFIED", "pod_verified",
            "delivery_success", "COMPLETED"
        )
        or "variance_min" in e.get("details", {})
        or "delay_minutes" in e.get("details", {})
        or ("planned_eta" in e.get("details", {}) and "actual_arrival" in e.get("details", {}))
    ]

    # If store has no delivery events, populate with default historical records
    if len(delivery_events) < 3:
        default_events = get_default_historical_events()
        for evt in default_events:
            target_store.set("events", evt["event_id"], evt)
        delivery_events = default_events

    # 2. Compute updated eta_buffer_min per pincode & hour band
    variance_data = compute_eta_variance(delivery_events)
    pincode_buffers: Dict[str, int] = variance_data["pincode_buffers"]
    by_pincode: Dict[str, Any] = variance_data["by_pincode"]

    # 3. Compute metrics summary (before, after, reduction_pct)
    metrics_summary = compute_metrics_summary(delivery_events, variance_data)

    # 4. Generate text proposal diff (never auto-modifies files)
    suggested_diff = generate_prompt_diff(pincode_buffers, by_pincode)

    # 5. Persist updated postal buffers into store.tuning
    now_iso = datetime.now(timezone.utc).isoformat()
    tuning_updates: Dict[str, TuningUpdate] = {}

    for pin, pin_info in by_pincode.items():
        reasons = pin_info.get("failure_reasons", [])
        primary_band = (
            list(pin_info.get("hour_bands", {}).keys())[0]
            if pin_info.get("hour_bands")
            else "09-12"
        )
        mean_err = pin_info.get("mean_error_min", 0.0)
        buf_min = pin_info.get("eta_buffer_min", 0)

        update = TuningUpdate(
            tuning_id=f"tune_{pin}_{uuid.uuid4().hex[:6]}",
            pincode=pin,
            eta_buffer_min=buf_min,
            hour_band=primary_band,
            predicted_error_min=mean_err,
            failure_reasons=reasons[:3],
            suggested_prompt_diff=suggested_diff,
            reason=(
                f"Historical delay variance of {mean_err:.1f}m observed across "
                f"{pin_info.get('sample_count', 0)} deliveries. "
                f"Primary factors: {', '.join(reasons[:2]) or 'traffic bottlenecks'}."
            ),
            updated_at=now_iso,
        )
        target_store.set("tuning", pin, update)
        tuning_updates[pin] = update

    # 6. Emit TUNING_APPLIED event to store.events
    event_id = f"evt_tuning_{uuid.uuid4().hex[:8]}"
    applied_event = Event(
        event_id=event_id,
        event_type="TUNING_APPLIED",
        source="feedback",
        timestamp=now_iso,
        details={
            "updated_pincodes": list(pincode_buffers.keys()),
            "buffers": pincode_buffers,
            "metrics": metrics_summary,
            "suggested_prompt_diff": suggested_diff,
            "sample_count": metrics_summary.get("sample_count", len(delivery_events)),
        },
    )
    target_store.set("events", event_id, applied_event)

    # 7. Return primary TuningUpdate instance
    if tuning_updates:
        # Pick the pincode with the largest buffer / error as the primary TuningUpdate
        primary_pin = max(
            tuning_updates.keys(),
            key=lambda p: (
                tuning_updates[p].eta_buffer_min,
                tuning_updates[p].predicted_error_min or 0.0,
            ),
        )
        return tuning_updates[primary_pin]

    return TuningUpdate(
        pincode="600000",
        eta_buffer_min=0,
        reason="No delivery events available for tuning.",
        updated_at=now_iso,
    )


def build_agent():
    """Build and export Google ADK Feedback Agent."""
    from google.adk.agents import Agent

    def feedback_tool() -> str:
        """Execute continuous feedback cycle to compute ETA error variance and update tuning buffers."""
        update = run_feedback_cycle()
        return json.dumps(update.model_dump())

    agent = Agent(
        name="feedback",
        model="gemini-2.5-flash",
        description="Continuous learning and feedback loop agent analyzing delivery ETA variances.",
        instruction=(
            "You are the Feedback Agent for DispatchMind. "
            "You analyze historical ETA prediction errors grouped by postal code and hour band. "
            "You compute recommended buffer adjustments to eliminate systematic delivery delays. "
            "Propose prompt and constraint improvements as text diffs. "
            "Never directly modify configuration files or prompts. "
            "Do not use em dashes in your response."
        ),
        tools=[feedback_tool],
    )
    return agent
