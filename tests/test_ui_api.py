import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_root_serves_html():
    res = client.get("/")
    assert res.status_code == 200
    assert "DispatchMind" in res.text
    assert "Break Something" in res.text

def test_static_assets_available():
    res_css = client.get("/static/styles.css")
    assert res_css.status_code == 200
    assert "--bg-primary" in res_css.text

    res_js = client.get("/static/app.js")
    assert res_js.status_code == 200
    assert "DispatchMind Dashboard Client Engine" in res_js.text

def test_events_stream():
    res = client.get("/events")
    assert res.status_code == 200
    events = res.json()
    assert isinstance(events, list)
    assert len(events) >= 1

def test_chat_interaction():
    res = client.post("/chat", json={"message": "Where is vehicle TN-09-AB-1234?"})
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert "TN-09-AB-1234" in data["reply"]

def test_valid_document_upload():
    sample_file = Path("data/sample_orders/INV-2026-001.pdf")
    assert sample_file.exists(), "Sample order INV-2026-001.pdf must exist"

    with open(sample_file, "rb") as f:
        res = client.post("/upload", files={"file": ("INV-2026-001.pdf", f, "application/pdf")})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert data["has_gap"] is False
        assert data["extracted_fields"]["pincode"] == "600017"

def test_gap_document_upload_triggers_clarification():
    sample_gap = Path("data/sample_orders/INV-2026-005-GAP.pdf")
    assert sample_gap.exists(), "Sample order INV-2026-005-GAP.pdf must exist"

    with open(sample_gap, "rb") as f:
        res = client.post("/upload", files={"file": ("INV-2026-005-GAP.pdf", f, "application/pdf")})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "CLARIFICATION_REQUIRED"
        assert data["has_gap"] is True
        assert data["missing_field"] == "pincode"
        assert "pincode" in data["question"].lower()

def test_route_plan_endpoint():
    res = client.post("/plan")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "OPTIMAL"
    assert len(data["vehicles"]) == 4

def test_failure_injection_scenarios():
    for f_type in ["breakdown", "traffic", "wrong_address", "rain"]:
        res = client.post(f"/inject/{f_type}")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "RECOVERED"
        assert "action" in data

def test_feedback_run():
    res = client.post("/feedback/run")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["tuning_metrics"]["reduction_pct"] == 75.0

def test_pod_submission():
    res = client.post("/pod", data={"order_id": "ORD-2026-104", "recipient_name": "S. Venkatachalam"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "DELIVERED"
    assert data["verification_confidence"] >= 0.9
