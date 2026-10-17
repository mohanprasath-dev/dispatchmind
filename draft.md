Here are the ready-to-paste starter prompts for each parallel agent thread, organized according to the roles in [EXECUTION_PLAN.md](file:///d:/TaskDrift/dispatchmind/EXECUTION_PLAN.md) and phases in [build_phases.json](file:///d:/TaskDrift/dispatchmind/build_phases.json).

---

### Prompt for Agent B: Backend, Core Foundation & MCP (Track B)
> **Role:** Start this agent first or in parallel with P0. It establishes the shared models, store, resilience layer, and MCP servers that the other agents depend on.

```markdown
You are Agent B (Backend & Core Lead) for DispatchMind.
Read AGENTS.md, PRD.md, and build_phases.json before starting.

YOUR MISSION: Implement Phase P0 (Scaffold & Store) and Phase P1 (Resilience Layer).

PHASE P0 TASKS:
1. Create the repository directory structure:
   - core/
   - mcp_servers/
   - agents/
   - app/static/
   - data/sample_orders/
   - tests/
2. Write requirements.txt with:
   google-adk, fastmcp, ortools, fastapi, uvicorn, pydantic, httpx, google-cloud-firestore, python-dotenv, pytest
3. Create .gitignore and .env.example (DEMO_MODE=true, GOOGLE_API_KEY, etc.). Never commit real secrets.
4. Create core/config.py:
   - Load environment variables with safe defaults and DEMO_MODE flag.
5. Create core/models.py with Pydantic v2 models:
   - Order, Vehicle, Driver, RoutePlan, Stop, Alert, RecoveryAction, PODResult, TuningUpdate, MissingFields.
   - Key Order fields: id, customer_name, phone, address, pincode, lat, lng, weight_kg, window_start, window_end, status, assigned_vehicle, eway_bill_no, gstin.
6. Create core/store.py:
   - Unified interface supporting Firestore and local JSON file fallback when DEMO_MODE=true.
   - Collections: orders, vehicles, drivers, routes, events, tuning, messages, pod.
7. Create data/seed.json and core/seed.py:
   - 12 realistic orders around Chennai (pincodes, time windows, weights), 4 vehicles, 4 drivers.

PHASE P1 TASKS:
1. Create core/resilience.py:
   - Decorator @resilient(fallback=None, retries=3, backoff="exp").
   - On final failure: call fallback, log event to events collection, return Degraded result.
   - Include escalation hook creating a "needs_human" event.
2. Create tests/test_resilience.py and tests/test_store.py.

CONSTRAINTS:
- No em dashes in code comments or docstrings.
- Python 3.11 compatible.
- Acceptance criteria: pytest passes for store and resilience, and python -m core.seed populates data.
```

---

### Prompt for Agent A: Agents & ADK Logic (Track A)
> **Role:** Implements the agent roster starting with Intake and Planner according to the contracts in [AGENTS.md](file:///d:/TaskDrift/dispatchmind/AGENTS.md).

```markdown
You are Agent A (Agents & ADK Specialist) for DispatchMind.
Read AGENTS.md, PRD.md, and build_phases.json before starting.

YOUR MISSION: Implement Phase P3 (Multi-modal Intake Agent) and Phase P4 (Planner Agent).

PHASE P3 (INTAKE AGENT) TASKS:
1. Create agents/intake.py exporting build_agent():
   - Multi-modal agent using Gemini (gemini-2.5-flash) to parse invoices, e-way bills, label photos, PDFs, or raw text.
   - Extract: order_id, customer, phone, address, pincode, weight_kg, time_window, GSTIN, eway_bill_no.
   - Validation rules: 6-digit Indian pincode, 10-digit Indian phone, positive weight.
   - Never invent or hallucinate missing data. Return MissingFields with exactly one precise question per gap.
   - Confidence scoring per field. Confidence < 0.6 triggers a human question.
   - Output Pydantic model: Order or MissingFields.
2. Create tests/test_intake.py testing extraction and validation.

PHASE P4 (PLANNER AGENT) TASKS:
1. Create agents/planner.py exporting build_agent():
   - Capacity and time-window vehicle routing problem (VRP) using Google OR-Tools.
   - Do NOT use Gemini for the math; use Gemini only to explain the resulting plan in plain English.
   - Distance matrix computed via maps MCP tool (with haversine x 1.4 fallback).
   - Apply eta_buffer_min per pincode from tuning collection.
   - Output RoutePlan with vehicle stop sequence, ETAs, total km, and list of unassigned orders with specific reasons.
2. Create tests/test_planner.py verifying capacity constraints and time windows for 12 orders and 4 vehicles in under 15 seconds.

CONSTRAINTS:
- All agent IO must use Pydantic models from core/models.py. No free text between agents.
- No em dashes in prompts or output copy.
```

---

### Prompt for Agent C: UI, Demo Experience & Test Assets (Track C)
> **Role:** Builds the client-side single-page dashboard, sample invoice assets, and the failure injection controls.

```markdown
You are Agent C (UI, Demo & Frontend Specialist) for DispatchMind.
Read AGENTS.md, PRD.md, and build_phases.json before starting.

YOUR MISSION: Implement Phase P8 UI shell, sample data assets, and failure injection panel.

TASKS:
1. Generate sample documents in data/sample_orders/:
   - 5 realistic sample invoice and e-way bill images/PDFs for Indian logistics (Chennai addresses, GSTIN, weights, 6-digit pincodes).
   - Include 1 invoice with an intentional gap (missing pincode or phone) to demonstrate the Intake agent asking a clarifying question.
2. Create app/static/index.html (and vanilla CSS/JS in app/static/):
   - Clean, professional, dark/modern logistics dispatch dashboard.
   - Single page layout containing:
     a) Dispatcher Chat & Intake Upload panel (drag-and-drop invoice photo/PDF).
     b) Route Planning Table (vehicles, assigned order sequence, ETAs, total km).
     c) Live Event Log (real-time stream showing alerts, recoveries, communications).
     d) "Break Something" Failure Injection panel (buttons for: Vehicle Breakdown, Traffic Delay, Wrong Address, Rain Alert).
     e) POD Submission simulator (driver photo upload).
     f) Before / After Feedback Card showing ETA error improvement.
3. Wire the UI to communicate with FastAPI endpoints in app/main.py:
   - POST /chat
   - POST /upload
   - POST /plan
   - GET /events
   - POST /inject/{failure_type}
   - POST /feedback/run

CONSTRAINTS:
- Use plain HTML, Vanilla CSS, and modern JavaScript. No complex frontend frameworks (React/Next).
- Mobile responsive and premium aesthetic.
- No em dashes in copy or UI text.
```

---

### Recommended Execution Strategy
1. **Paste Prompt B** into an agent session right now to create `core/models.py`, `core/store.py`, and `requirements.txt`.
2. As soon as `core/models.py` is in place, **paste Prompt A and Prompt C** into their respective parallel sessions.

If you would like this current session to start immediately as **Agent B** (scaffolding P0 & P1), let me know and I will begin right away!