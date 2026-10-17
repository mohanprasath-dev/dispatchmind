"""Orchestrator Agent for DispatchMind.

Root router agent coordinating multi-agent dispatch workflows:
- Routes dispatcher queries and events to specialized sub-agents
- Sub-agents: Intake, Planner, Monitor, Recovery, Comms, POD, Feedback
- Exposes build_agent() for Google ADK and adk web CLI loading
"""

import json
import logging
from typing import Dict, Any, Optional

from core.store import store
from agents.intake import build_agent as build_intake_agent, process_intake
from agents.planner import build_agent as build_planner_agent, plan_day
from agents.monitor import build_agent as build_monitor_agent, check_active_routes
from agents.recovery import build_agent as build_recovery_agent, recover_alert
from agents.comms import (
    build_agent as build_comms_agent,
    generate_dispatcher_reply,
    format_eta_update,
)
from agents.pod import build_agent as build_pod_agent, process_pod
from agents.feedback import build_agent as build_feedback_agent, run_feedback_cycle

logger = logging.getLogger(__name__)


def route_intent(query: str) -> str:
    """Classify user intent to select the appropriate specialized sub-agent."""
    q = query.lower()
    if any(k in q for k in ["invoice", "e-way", "eway", "challan", "upload", "parse doc", "intake", "bill"]):
        return "intake"
    if any(k in q for k in ["plan", "route", "optimize", "schedule", "assign vehicles", "generate routes"]):
        return "planner"
    if any(k in q for k in ["monitor", "status", "drift", "delay", "idle", "weather risk", "check fleet"]):
        return "monitor"
    if any(k in q for k in ["breakdown", "accident", "recover", "reassign", "resequence", "puncture", "failure"]):
        return "recovery"
    if any(k in q for k in ["pod", "proof of delivery", "photo", "sign", "signature", "delivered"]):
        return "pod"
    if any(k in q for k in ["feedback", "tuning", "buffer", "variance", "accuracy", "historical error"]):
        return "feedback"
    if any(k in q for k in ["message", "sms", "whatsapp", "telegram", "notify", "tamil", "hindi"]):
        return "comms"
    return "comms"


def handle_dispatch_chat(message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handle conversational chat query from the dispatcher dashboard.
    Routes to the correct sub-agent and formats a concise response.
    """
    intent = route_intent(message)
    context = context or {}

    if intent == "planner":
        try:
            plan = plan_day()
            summary = (
                f"Generated route plan for {len(plan.routes)} vehicles. "
                f"Total distance: {plan.total_km:.1f} km. "
                f"Assigned orders: {sum(len(r.stops) for r in plan.routes)}. "
                f"Unassigned: {len(plan.unassigned_orders)}."
            )
            return {
                "intent": "planner",
                "reply": summary,
                "data": plan.model_dump(),
                "agent": "PlannerAgent"
            }
        except Exception as e:
            return {
                "intent": "planner",
                "reply": f"Route planning encountered an issue: {str(e)}",
                "error": str(e),
                "agent": "PlannerAgent"
            }

    elif intent == "monitor":
        alerts = check_active_routes()
        if alerts:
            alert_descs = [f"[{a.severity}] {a.alert_type}: {a.message}" for a in alerts[:3]]
            reply = f"Fleet health check flagged {len(alerts)} alerts:\n" + "\n".join(alert_descs)
        else:
            reply = "Fleet monitoring active: All routes operating within normal parameters. Zero critical delays detected."
        return {
            "intent": "monitor",
            "reply": reply,
            "alerts": [a.model_dump() for a in alerts],
            "agent": "MonitorAgent"
        }

    elif intent == "feedback":
        update = run_feedback_cycle(store)
        tuning_records = store.list("tuning")
        reply = (
            f"Feedback cycle completed. Updated delivery buffers for pincode {update.pincode} "
            f"to +{update.eta_buffer_min}m (tuned across {len(tuning_records)} active corridors). "
            f"Historical delay variance mitigated."
        )
        return {
            "intent": "feedback",
            "reply": reply,
            "data": update.model_dump(),
            "agent": "FeedbackAgent"
        }

    elif intent == "recovery":
        reply = "Recovery agent standby: Injected failures (breakdown, delay, address exception) will trigger automated self-healing."
        return {
            "intent": "recovery",
            "reply": reply,
            "agent": "RecoveryAgent"
        }

    elif intent == "pod":
        reply = "POD agent standby: Submit delivery photo to verify package presence, geotag, and recipient signature."
        return {
            "intent": "pod",
            "reply": reply,
            "agent": "PODAgent"
        }

    else:
        # Default conversational routing via Comms Agent
        state_summary = {
            "active_vehicles": len(store.list("vehicles")),
            "open_orders": len(store.list("orders")),
            "recent_events": len(store.list("events")),
        }
        reply = generate_dispatcher_reply(message, state_summary=state_summary)
        return {
            "intent": "comms",
            "reply": reply,
            "agent": "CommsAgent"
        }


def build_agent():
    """Build and export Google ADK Root Orchestrator Agent."""
    from google.adk.agents import Agent

    sub_agents = [
        build_intake_agent(),
        build_planner_agent(),
        build_monitor_agent(),
        build_recovery_agent(),
        build_comms_agent(),
        build_pod_agent(),
        build_feedback_agent(),
    ]

    agent = Agent(
        name="orchestrator",
        model="gemini-2.5-flash",
        description="DispatchMind Root Router and Orchestrator Agent.",
        instruction=(
            "You are the master Orchestrator for DispatchMind, an autonomous dispatch co-pilot for Indian fleets. "
            "Route dispatcher instructions to appropriate sub-agents: "
            "intake for logistics documents, planner for OR-Tools route generation, "
            "monitor for live telemetry and weather risks, recovery for self-healing vehicle disruptions, "
            "comms for multilingual customer/driver messaging, pod for delivery proof verification, "
            "and feedback for continuous pincode learning. "
            "Keep responses concise and professional. Do not use em dashes."
        ),
        sub_agents=sub_agents,
    )
    return agent


# Export root agent for ADK web discovery
agent = build_agent()
