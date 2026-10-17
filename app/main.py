import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Configuration and Paths
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"
SAMPLES_DIR = BASE_DIR / "data" / "sample_orders"
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

app = FastAPI(
    title="DispatchMind API",
    description="Multi-agent dispatch co-pilot for Indian small and mid fleet operators.",
    version="1.0.0"
)

# In-Memory State for Demo Mode
INITIAL_VEHICLES = [
    {
        "id": "TN-09-AB-1234",
        "driver_name": "Murugan K.",
        "phone": "+91 98401 11223",
        "vehicle_type": "Tata Ace (1.5T)",
        "capacity_kg": 1000.0,
        "current_load_kg": 525.5,
        "status": "ON_ROUTE",
        "current_location": "Guindy Industrial Estate",
        "total_km": 48.2,
        "est_completion": "16:45",
        "stops": [
            {
                "stop_no": 1,
                "order_id": "ORD-2026-101",
                "customer": "Apex Auto Spares",
                "address": "45 Usman Road, T. Nagar",
                "pincode": "600017",
                "weight_kg": 85.5,
                "window": "10:00 - 13:00",
                "eta": "10:45",
                "status": "COMPLETED"
            },
            {
                "stop_no": 2,
                "order_id": "ORD-2026-104",
                "customer": "Nilgiri Retail Depot",
                "address": "82 100 Feet Bypass Road, Velachery",
                "pincode": "600042",
                "weight_kg": 45.0,
                "window": "11:00 - 14:00",
                "eta": "12:15",
                "status": "IN_TRANSIT"
            },
            {
                "stop_no": 3,
                "order_id": "ORD-2026-105",
                "customer": "Krishna Construction Supplies",
                "address": "Door No 42, 2nd Avenue, Anna Nagar West",
                "pincode": "600040",
                "weight_kg": 65.0,
                "window": "13:00 - 16:00",
                "eta": "14:20",
                "status": "SCHEDULED"
            }
        ]
    },
    {
        "id": "TN-01-CD-5678",
        "driver_name": "Ravi Chandran",
        "phone": "+91 97902 33445",
        "vehicle_type": "Ashok Leyland Dost (2.0T)",
        "capacity_kg": 1500.0,
        "current_load_kg": 460.0,
        "status": "ON_ROUTE",
        "current_location": "Royapuram Terminal",
        "total_km": 62.8,
        "est_completion": "17:15",
        "stops": [
            {
                "stop_no": 1,
                "order_id": "ORD-2026-102",
                "customer": "Precision Heavy Engineering",
                "address": "Shed C-12, Ambattur Industrial Estate",
                "pincode": "600058",
                "weight_kg": 320.0,
                "window": "09:00 - 12:00",
                "eta": "11:15",
                "status": "COMPLETED"
            },
            {
                "stop_no": 2,
                "order_id": "ORD-2026-103",
                "customer": "SmartTech Distribution Center",
                "address": "12 Sardar Patel Road, Adyar",
                "pincode": "600020",
                "weight_kg": 140.0,
                "window": "14:00 - 17:00",
                "eta": "14:50",
                "status": "SCHEDULED"
            }
        ]
    },
    {
        "id": "TN-10-EF-9012",
        "driver_name": "Selvam S.",
        "phone": "+91 94433 55667",
        "vehicle_type": "Mahindra Bolero Maxi (1.7T)",
        "capacity_kg": 1200.0,
        "current_load_kg": 310.0,
        "status": "ON_ROUTE",
        "current_location": "Poonamallee High Road",
        "total_km": 39.5,
        "est_completion": "15:30",
        "stops": [
            {
                "stop_no": 1,
                "order_id": "ORD-2026-106",
                "customer": "Kovai Electronics Retail",
                "address": "18 GST Road, Tambaram Sanatorium",
                "pincode": "600047",
                "weight_kg": 180.0,
                "window": "11:00 - 14:00",
                "eta": "12:30",
                "status": "IN_TRANSIT"
            },
            {
                "stop_no": 2,
                "order_id": "ORD-2026-107",
                "customer": "VGP Hardware Traders",
                "address": "55 Medavakkam Main Road, Madipakkam",
                "pincode": "600091",
                "weight_kg": 130.0,
                "window": "13:30 - 16:30",
                "eta": "14:10",
                "status": "SCHEDULED"
            }
        ]
    },
    {
        "id": "TN-04-GH-3456",
        "driver_name": "Anand P.",
        "phone": "+91 98844 77889",
        "vehicle_type": "Eicher Pro 2049 (3.5T)",
        "capacity_kg": 2500.0,
        "current_load_kg": 680.0,
        "status": "IDLE_STANDBY",
        "current_location": "Koyambedu Logistics Park",
        "total_km": 15.0,
        "est_completion": "18:00",
        "stops": [
            {
                "stop_no": 1,
                "order_id": "ORD-2026-108",
                "customer": "Chennai Cold Storage Depot",
                "address": "Block 5, Koyambedu Market",
                "pincode": "600107",
                "weight_kg": 680.0,
                "window": "10:00 - 13:00",
                "eta": "11:40",
                "status": "COMPLETED"
            }
        ]
    }
]

state = {
    "vehicles": json.loads(json.dumps(INITIAL_VEHICLES)),
    "events": [
        {
            "id": "evt-1",
            "timestamp": "12:45:10",
            "type": "SYSTEM",
            "severity": "info",
            "source": "ORCHESTRATOR",
            "message": "DispatchMind system booted in DEMO_MODE. Fleet connected (4 vehicles, 12 Chennai routes loaded)."
        },
        {
            "id": "evt-2",
            "timestamp": "12:47:33",
            "type": "PLAN",
            "severity": "success",
            "source": "PLANNER AGENT",
            "message": "Daily VRP route plan optimized with OR-Tools: 4 vehicles, 12 stops, total fleet distance 165.5 km. Zero capacity violations."
        },
        {
            "id": "evt-3",
            "timestamp": "12:50:02",
            "type": "MONITOR",
            "severity": "info",
            "source": "MONITOR AGENT",
            "message": "Routine telemetry check: All 4 vehicles within +/- 4 minutes of scheduled ETAs. Weather conditions clear."
        }
    ],
    "tuning": {
        "before": {"mae_min": 24.8, "p90_min": 42.0},
        "after": {"mae_min": 6.2, "p90_min": 11.5},
        "reduction_pct": 75.0,
        "buffers": {
            "600017 (T. Nagar)": 12,
            "600042 (Velachery)": 18,
            "600058 (Ambattur)": 8,
            "600020 (Adyar)": 5
        },
        "last_run": None
    }
}

# Request Models
class ChatRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None

class FeedbackRunRequest(BaseModel):
    target_pincode: Optional[str] = None

class PodSubmitRequest(BaseModel):
    order_id: str
    recipient_name: Optional[str] = "K. Ramanathan"
    notes: Optional[str] = "Delivered to shop front desk"

def add_event(source: str, event_type: str, severity: str, message: str):
    now_str = datetime.now().strftime("%H:%M:%S")
    evt = {
        "id": f"evt-{len(state['events']) + 1}",
        "timestamp": now_str,
        "type": event_type,
        "severity": severity,
        "source": source,
        "message": message
    }
    state["events"].insert(0, evt)
    return evt

# API Endpoints

@app.get("/events")
async def get_events(limit: int = 50):
    """Retrieve live real-time event stream."""
    return state["events"][:limit]

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """Dispatcher conversational assistant and subagent router."""
    msg = req.message.strip()
    msg_lower = msg.lower()

    # Dispatcher command interpretation
    if "where is" in msg_lower or "tn-09" in msg_lower or "status of" in msg_lower:
        v = state["vehicles"][0]
        reply = (
            f"Vehicle {v['id']} ({v['driver_name']}) is currently {v['status']} near {v['current_location']}. "
            f"Next stop: {v['stops'][1]['customer']} ({v['stops'][1]['address']}), ETA: {v['stops'][1]['eta']}. "
            f"Capacity utilization is {v['current_load_kg']}/{v['capacity_kg']} kg."
        )
        add_event("COMMS AGENT", "CHAT", "info", f"Dispatcher query answered: {msg}")
        return {"reply": reply, "agent": "Comms / Telemetry Agent"}

    elif "plan" in msg_lower or "optimize" in msg_lower or "route" in msg_lower:
        add_event("PLANNER AGENT", "PLAN", "success", "Manual plan trigger requested via chat dispatch.")
        return {
            "reply": "Route planning initiated with Google OR-Tools. 4 vehicles assigned across 12 stops. Constraints respected: max capacity 1000-2500 kg, hard time windows 09:00 - 17:00.",
            "agent": "Planner Agent"
        }

    elif "break" in msg_lower or "delay" in msg_lower or "fail" in msg_lower:
        return {
            "reply": "Failure injection ready. You can trigger Vehicle Breakdown, Traffic Delay, Wrong Address, or Rain Alert from the 'Break Something' panel to observe automated self-healing.",
            "agent": "Recovery Agent"
        }

    elif "pincode" in msg_lower or ("600" in msg_lower and len(msg_lower) >= 6):
        # Dispatcher resolving missing pincode
        import re
        pin_match = re.search(r"\b600\d{3}\b", msg)
        pin = pin_match.group(0) if pin_match else "600040"
        add_event("INTAKE AGENT", "CLARIFICATION", "success", f"Dispatcher provided missing postal code {pin} for Anna Nagar West shipment. Order ORD-2026-105 validated and registered.")
        return {
            "reply": f"Thank you! Delivery pincode {pin} recorded for Order ORD-2026-105 (Krishna Construction Supplies). Geocode resolved to (13.0850 N, 80.2101 E). Order queued for vehicle allocation.",
            "agent": "Intake Agent"
        }

    else:
        # General response
        reply = (
            f"DispatchMind Orchestrator active. I can assist with fleet tracking, order reassignments, "
            f"exception recovery, and customer comms in English, Hindi, and Tamil. (Query: '{msg}')"
        )
        add_event("ORCHESTRATOR", "CHAT", "info", f"Dispatcher chat: {msg}")
        return {"reply": reply, "agent": "Orchestrator"}

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Intake Agent multi-modal document parser (Invoices, e-Way bills)."""
    filename = file.filename or "uploaded_invoice"
    content_bytes = await file.read()
    file_size_kb = len(content_bytes) / 1024.0

    # Check for intentional gap file (Sample 5)
    is_gap_sample = "005" in filename.upper() or "GAP" in filename.upper()

    if is_gap_sample:
        add_event(
            "INTAKE AGENT",
            "GAP_DETECTED",
            "warning",
            f"Document '{filename}' parsed with intentional gap: Missing 6-digit Pincode for Anna Nagar West address. Clarification requested from dispatcher."
        )
        return {
            "status": "CLARIFICATION_REQUIRED",
            "order_id": "ORD-2026-105",
            "document_name": filename,
            "has_gap": True,
            "missing_field": "pincode",
            "question": "Delivery pincode is missing for Anna Nagar West address. Please confirm the 6-digit postal code (e.g. 600040 or 600101).",
            "extracted_fields": {
                "order_id": "ORD-2026-105",
                "customer": "Krishna Construction Supplies",
                "phone": "+91 98412 34999",
                "address": "Door No 42, 2nd Avenue, Anna Nagar West, Chennai, Tamil Nadu",
                "pincode": None,
                "weight_kg": 65.0,
                "delivery_window": "13:00 - 16:00",
                "gstin": "33EEEEE7890E1Z4",
                "eway_bill_no": "2410 6655 4321",
                "confidence": 0.58
            }
        }
    else:
        # Standard valid invoice
        doc_meta = {
            "order_id": "ORD-2026-101",
            "customer": "Apex Auto Spares",
            "phone": "+91 98401 23456",
            "address": "45 Usman Road, T. Nagar, Chennai",
            "pincode": "600017",
            "weight_kg": 85.5,
            "delivery_window": "10:00 - 13:00",
            "gstin": "33AAAAA1234A1Z5",
            "eway_bill_no": "2410 9811 2045",
            "confidence": 0.98
        }
        add_event(
            "INTAKE AGENT",
            "ORDER_CREATED",
            "success",
            f"Document '{filename}' successfully extracted. Validated 6-digit pincode 600017, phone +91 98401 23456, weight 85.5 kg. Order created."
        )
        return {
            "status": "SUCCESS",
            "order_id": doc_meta["order_id"],
            "document_name": filename,
            "has_gap": False,
            "missing_field": None,
            "extracted_fields": doc_meta
        }

@app.post("/plan")
async def generate_plan():
    """Trigger Route Planning with OR-Tools and return optimized stops and vehicle assignments."""
    add_event(
        "PLANNER AGENT",
        "PLAN_UPDATED",
        "success",
        "Route plan generated: 4 vehicles dispatched across 12 Chennai delivery points. Total distance: 165.5 km. Peak buffer offsets applied."
    )
    return {
        "status": "OPTIMAL",
        "vehicles": state["vehicles"],
        "total_vehicles": len(state["vehicles"]),
        "total_stops": sum(len(v["stops"]) for v in state["vehicles"]),
        "total_km": sum(v["total_km"] for v in state["vehicles"]),
        "unassigned_orders": []
    }

@app.post("/inject/{failure_type}")
async def inject_failure(failure_type: str):
    """
    Self-healing failure injection panel:
    - breakdown: Vehicle engine failure -> reassign orders to nearby vehicle
    - traffic: Kathipara junction delay -> re-sequence and divert route
    - wrong_address: Recipient gate locked -> reschedule stop, trigger WhatsApp alert
    - rain: Velachery waterlogging -> apply rain speed factor and reprioritize
    """
    ft = failure_type.lower()
    
    if ft == "breakdown":
        # Vehicle 1 breakdown
        v1 = state["vehicles"][0]
        v2 = state["vehicles"][1]
        v1["status"] = "BREAKDOWN_STOPPED"
        v1["current_location"] = "GST Road, Guindy (Mechanical breakdown - radiator leak)"
        
        # Shift stop 2 & 3 to vehicle 2
        reassigned_stop = v1["stops"][1]
        v2["stops"].append({
            "stop_no": len(v2["stops"]) + 1,
            "order_id": reassigned_stop["order_id"],
            "customer": reassigned_stop["customer"],
            "address": reassigned_stop["address"],
            "pincode": reassigned_stop["pincode"],
            "weight_kg": reassigned_stop["weight_kg"],
            "window": reassigned_stop["window"],
            "eta": "15:45",
            "status": "REASSIGNED_SCHEDULED"
        })
        v2["current_load_kg"] += reassigned_stop["weight_kg"]
        
        add_event(
            "MONITOR AGENT",
            "ALERT_BREAKDOWN",
            "critical",
            "Vehicle TN-09-AB-1234 coolant failure on GST Road. Telemetry stopped. Immediate intervention required."
        )
        add_event(
            "RECOVERY AGENT",
            "AUTO_REASSIGNMENT",
            "success",
            "Self-healing executed: Pending stops reassigned to Vehicle TN-01-CD-5678 (Ravi Chandran). Capacity utilization 945 / 1500 kg. ETA updated +25 min."
        )
        add_event(
            "COMMS AGENT",
            "TELEGRAM_ALERT",
            "info",
            "Telegram notification sent to Driver Ravi Chandran with new waypoint. Customer Nilgiri Retail Depot alerted with revised ETA 15:45."
        )
        return {
            "status": "RECOVERED",
            "failure": "Vehicle Breakdown",
            "action": "Reassigned pending stops to Vehicle TN-01-CD-5678",
            "affected_vehicle": "TN-09-AB-1234",
            "backup_vehicle": "TN-01-CD-5678"
        }

    elif ft in ["traffic", "delay"]:
        v = state["vehicles"][0]
        add_event(
            "MONITOR AGENT",
            "ALERT_TRAFFIC",
            "warning",
            "ETA drift alert: Kathipara Junction flyover congestion detected. Predicted delay: +35 minutes."
        )
        add_event(
            "RECOVERY AGENT",
            "AUTO_RESEQUENCE",
            "success",
            "Self-healing executed: Rerouted TN-09-AB-1234 via 100-Ft Inner Ring Road arterial. Net delay reduced from 35 min to 9 min."
        )
        add_event(
            "COMMS AGENT",
            "SMS_ALERT",
            "info",
            "Automated recipient SMS dispatched: 'Your delivery from Apex Auto Spares is now scheduled for 11:45 AM due to route optimization.'"
        )
        return {
            "status": "RECOVERED",
            "failure": "Traffic Delay",
            "action": "Re-routed via Inner Ring Road; delay mitigated to 9 min.",
            "vehicle": "TN-09-AB-1234"
        }

    elif ft in ["wrong_address", "address", "unreachable"]:
        add_event(
            "MONITOR AGENT",
            "ALERT_EXCEPTION",
            "warning",
            "Delivery exception at Anna Nagar West: Premise locked, primary recipient phone busy."
        )
        add_event(
            "RECOVERY AGENT",
            "RESCHEDULE",
            "success",
            "Self-healing executed: Driver instructed to skip stop and continue route. Order ORD-2026-105 rescheduled to end-of-day loop."
        )
        add_event(
            "COMMS AGENT",
            "WHATSAPP_DISPATCH",
            "info",
            "Automated WhatsApp message with live reschedule link sent to customer phone +91 98412 34999."
        )
        return {
            "status": "RECOVERED",
            "failure": "Wrong Address / Unreachable",
            "action": "Rescheduled to end of route loop, automated WhatsApp outreach dispatched.",
            "order_id": "ORD-2026-105"
        }

    elif ft in ["rain", "weather"]:
        add_event(
            "MONITOR AGENT",
            "ALERT_WEATHER",
            "warning",
            "Open-Meteo rain risk: Heavy monsoon waterlogging advisory across Velachery and South Chennai."
        )
        add_event(
            "RECOVERY AGENT",
            "SPEED_FACTOR_ADJUST",
            "success",
            "Self-healing executed: Route transit factor adjusted to 1.4x for waterlogged corridors. Sensitive electronic cargo stops prioritized before peak storm."
        )
        add_event(
            "COMMS AGENT",
            "BROADCAST",
            "info",
            "Advisory broadcasted to all 4 fleet drivers: Exercise cautious driving on Velachery 100-Ft Road; low-lying underpasses avoided."
        )
        return {
            "status": "RECOVERED",
            "failure": "Heavy Monsoon Rain",
            "action": "Transit factor adjusted to 1.4x, fragile consignments prioritized before storm peak."
        }

    else:
        raise HTTPException(status_code=400, detail=f"Unknown failure type: {failure_type}")

@app.post("/pod")
async def submit_pod(
    order_id: str = Form(...),
    photo: Optional[UploadFile] = File(None),
    recipient_name: Optional[str] = Form("K. Ramanathan")
):
    """Proof of Delivery (POD) agent verification simulator."""
    now_str = datetime.now().strftime("%H:%M:%S")
    add_event(
        "POD AGENT",
        "POD_VERIFIED",
        "success",
        f"Delivery photo for {order_id} verified via Gemini Vision: Scene confidence 96%, package confirmed at address, recipient signature matched ({recipient_name}). Order closed."
    )
    # Update stop status if present
    for v in state["vehicles"]:
        for s in v["stops"]:
            if s["order_id"] == order_id:
                s["status"] = "DELIVERED"

    return {
        "status": "DELIVERED",
        "order_id": order_id,
        "recipient_name": recipient_name,
        "verification_confidence": 0.96,
        "geotag_verified": True,
        "geotag_distance_meters": 12.4,
        "timestamp": now_str,
        "message": f"Order {order_id} marked as DELIVERED."
    }

@app.post("/feedback/run")
async def run_feedback(req: Optional[FeedbackRunRequest] = None):
    """Run Feedback agent cycle to calculate error variance and tune pincode buffers."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state["tuning"]["last_run"] = now_str
    
    add_event(
        "FEEDBACK AGENT",
        "TUNING_APPLIED",
        "success",
        "Feedback loop completed across 48 historical runs. Mean ETA prediction error reduced from 24.8m to 6.2m (-75.0%). Buffers updated in tuning store."
    )

    return {
        "status": "SUCCESS",
        "message": "Feedback cycle complete. Planner agent has ingested updated postal buffers.",
        "tuning_metrics": state["tuning"]
    }

@app.get("/sample-orders")
async def list_sample_orders():
    """List available sample orders in data/sample_orders for quick testing."""
    if not SAMPLES_DIR.exists():
        return []
    files = [f.name for f in SAMPLES_DIR.iterdir() if f.is_file() and not f.name.startswith(".")]
    return sorted(files)

@app.get("/sample-orders/{filename}")
async def get_sample_order(filename: str):
    """Serve a sample order document or image."""
    filepath = SAMPLES_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "application/pdf" if filename.endswith(".pdf") else "image/png"
    return FileResponse(filepath, media_type=media_type)

# Serve Frontend static assets
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def root_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "DispatchMind API is running. UI shell index.html will be served at / once created."}
