"""Unit tests for DispatchMind Orchestrator Root Agent."""

import pytest
from agents.orchestrator import build_agent, handle_dispatch_chat, route_intent
from core.store import store


def test_orchestrator_build_agent():
    """Verify ADK root agent builds with all 7 sub-agents."""
    agent = build_agent()
    assert agent.name == "orchestrator"
    assert len(agent.sub_agents) == 7
    sub_names = [a.name for a in agent.sub_agents]
    assert "intake" in sub_names
    assert "planner" in sub_names
    assert "monitor" in sub_names
    assert "recovery" in sub_names
    assert "comms" in sub_names
    assert "pod" in sub_names
    assert "feedback" in sub_names


def test_route_intent():
    """Test intent classifier keywords."""
    assert route_intent("Upload invoice ORD-101") == "intake"
    assert route_intent("Plan the day routes for Chennai") == "planner"
    assert route_intent("Check fleet status and delays") == "monitor"
    assert route_intent("Vehicle breakdown on GST road") == "recovery"
    assert route_intent("Verify POD photo for delivery") == "pod"
    assert route_intent("Run feedback tuning cycle") == "feedback"
    assert route_intent("Send customer WhatsApp message in Tamil") == "comms"


def test_handle_dispatch_chat_planner():
    """Test routing chat request to planner sub-agent."""
    res = handle_dispatch_chat("Please plan the day routes")
    assert res["intent"] == "planner"
    assert res["agent"] == "PlannerAgent"
    assert "reply" in res


def test_handle_dispatch_chat_feedback():
    """Test routing chat request to feedback sub-agent."""
    res = handle_dispatch_chat("Run feedback loop")
    assert res["intent"] == "feedback"
    assert res["agent"] == "FeedbackAgent"
    assert "eta_buffer_min" in res["data"]
    assert "pincode" in res["data"]


def test_handle_dispatch_chat_comms():
    """Test general conversational query routing to comms agent."""
    res = handle_dispatch_chat("What is our fleet readiness today?")
    assert res["intent"] == "comms"
    assert res["agent"] == "CommsAgent"
    assert len(res["reply"]) > 0
