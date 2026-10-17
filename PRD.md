# PRD: DispatchMind

## 1. Summary
AI dispatch co-pilot that automates order intake, route planning, live monitoring, exception recovery, customer comms, and proof of delivery for small and mid fleet operators in India.

## 2. Problem
Dispatchers run operations over WhatsApp, calls, Excel, and paper. Result: manual entry errors, late delay discovery, failed deliveries, slow reassignment, and no dispute-proof delivery record.

## 3. Users
- **Primary:** dispatcher at a 10 to 200 vehicle fleet
- **Secondary:** driver (receives route, sends POD), receiver (gets ETA updates)

## 4. Goals and success metrics
| Goal | Metric (demo target) |
|---|---|
| Cut data entry | Order from photo to structured in < 30 s |
| Fewer surprises | Delay detected and customer notified in < 2 min |
| Fewer failed deliveries | Auto-recovery success on injected failures >= 80% |
| Better ETAs | ETA error drops after feedback cycle (show numbers) |
| Trust | Every order has POD record |

## 5. Non-goals
Billing, payroll, GPS hardware, native mobile apps, multi-tenant admin.

## 6. Features

### P0 (must ship)
1. **Multi-modal intake:** invoice, e-way bill, label photo or PDF to structured order, asks only for gaps.
2. **Route planning:** capacity and time-window VRP, per-vehicle sequence and ETAs.
3. **Live monitoring:** ETA drift, weather, idle detection with alerts.
4. **Self-healing recovery:** auto reroute or reassign, with human approval above threshold.
5. **Conversational dispatcher chat:** "Where is vehicle TN09...?", "Move order 112 to Ravi".
6. **Customer and driver messaging** via Telegram.
7. **POD agent:** photo verification and order closure.
8. **Feedback loop:** per-pincode ETA buffers learned from outcomes.
9. **MCP integration:** all tools behind MCP servers.
10. **Demo mode** with seed data and failure injection button.

### P1 (if time)
- Hindi and Tamil replies
- End-of-day report (PDF or markdown)
- Cost per delivery estimate

### P2 (cut)
Multi-depot, returns, dock scheduling.

## 7. User stories
- As a dispatcher, I upload an invoice photo and get a clean order or one precise question.
- As a dispatcher, I click "plan day" and see routes on a map with ETAs.
- As a dispatcher, I get a proposal when a truck is delayed and approve it in one tap.
- As a receiver, I get a message with the new ETA without calling anyone.
- As a driver, I send a delivery photo and the order closes.

## 8. Functional requirements
- FR1: Intake returns validated `Order` or `MissingFields`.
- FR2: Planner never exceeds vehicle capacity or violates hard time windows. Unassigned orders are explained.
- FR3: Monitor runs on interval and writes `Alert` events.
- FR4: Recovery logs action, reason, and result for each alert.
- FR5: Every tool call is wrapped by the resilience layer.
- FR6: Feedback updates `eta_buffer_min`; Planner consumes it.
- FR7: UI shows chat, route table or map, event log, and a "break something" panel.

## 9. Non-functional
- Run end to end with one env var (`GOOGLE_API_KEY`) in `DEMO_MODE`.
- p95 agent response < 8 s for chat, < 20 s for intake.
- Deployed on Cloud Run, public GitHub repo, README runnable A to Z.

## 10. Data model (Firestore collections)
`orders`, `vehicles`, `drivers`, `routes`, `events`, `tuning`, `messages`, `pod`

Key `Order` fields: id, customer_name, phone, address, pincode, lat, lng, weight_kg, window_start, window_end, status, assigned_vehicle, eway_bill_no, gstin.

## 11. Competition criteria mapping
| Criterion | Where met |
|---|---|
| Multi-modal agents | Intake, POD |
| Conversation agents | Comms, dispatcher chat |
| API calls | Maps Routes, Open-Meteo, Telegram, Gemini |
| MCP integration | `mcp_servers/` |
| Feedback loop | Feedback agent + `eta_buffer_min` |
| Self-healing agents | `core/resilience.py`, Recovery agent |
| A to Z instructions | README.md |

## 12. Pricing (proposal, validate with operators)
Starter Rs 499 per vehicle per month (up to 20), Pro Rs 899 (POD, messaging, analytics), Enterprise custom.

## 13. Risks
| Risk | Mitigation |
|---|---|
| API keys or quota fail in judging | `DEMO_MODE` with seed data and fallbacks |
| Gemini misreads documents | Confidence score, ask human on low confidence |
| Scope creep | P0 only until day 7 |
| Telegram setup friction for judges | Console channel fallback |
