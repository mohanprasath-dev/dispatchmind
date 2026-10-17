# AGENTS.md

Instructions for any coding agent (Antigravity, Gemini CLI, Claude Code) working in this repo, plus the runtime agent spec.

## Project
DispatchMind: multi-agent dispatch co-pilot for Indian small and mid fleet operators. Turns documents and chats into planned, monitored, self-correcting deliveries.

## Stack (fixed, do not swap)
- Python 3.11, Google ADK (`google-adk`), Gemini (`gemini-2.5-flash`)
- MCP servers via `fastmcp`, consumed in ADK through its MCP toolset
- Route planning: OR-Tools (VRP) + Google Maps Routes API (distance matrix). Fallback: haversine
- Weather: Open-Meteo (no key)
- Storage: Firestore. Fallback: local JSON store when `DEMO_MODE=true`
- Messaging: Telegram Bot API (driver and customer channel)
- Backend: FastAPI + minimal HTML chat UI. Deploy: Cloud Run

## Repo layout
```
dispatchmind/
  agents/            one file per agent, each exports `build_agent()`
  mcp_servers/       orders_server.py maps_server.py weather_server.py notify_server.py docs_server.py
  core/              resilience.py feedback.py config.py models.py store.py
  app/               main.py (FastAPI), static/ (chat UI)
  data/              sample_orders/ (invoice images, pdfs), seed.json
  tests/
  prompts/           build_phases.json
  docs/
```

## Commands
- Install: `pip install -r requirements.txt`
- Run all: `uvicorn app.main:app --reload`
- ADK dev UI: `adk web agents`
- Tests: `pytest -q`
- Demo seed: `python -m core.seed`

## Rules
1. No hardcoded secrets. Read from env via `core/config.py`. Keep `.env.example` current.
2. Every external call goes through `core/resilience.py` (retry 3x with backoff, then fallback, then escalate to human).
3. `DEMO_MODE=true` must work with only `GOOGLE_API_KEY` set. Judges will run it this way.
4. All agent inputs and outputs are Pydantic models in `core/models.py`. No free text between agents.
5. Agents never write to the DB directly. They call MCP tools.
6. Every failure and recovery is logged to the `events` collection (feeds the feedback loop and the demo).
7. Keep functions small. Add one test per agent minimum.
8. No em dashes in docs or user-facing copy.
9. Do not add features outside PRD.md P0 and P1.

## Runtime agent roster

| Agent | Type | Tools (MCP) | Input | Output |
|---|---|---|---|---|
| Orchestrator | root, router | sub-agents | chat or event | routed task, final answer |
| Intake | multi-modal | orders, docs | image, pdf, text | `Order` list + `MissingFields` |
| Planner | tool-using | maps, orders | open orders, fleet | `RoutePlan` |
| Monitor | scheduled | maps, weather, orders | active routes | `Alert` list |
| Recovery | self-healing | maps, orders, notify | `Alert` | `RecoveryAction` |
| Comms | conversational | notify, orders | any status change | messages, replies |
| POD | multi-modal | docs, orders | delivery photo | `PODResult` |
| Feedback | batch | orders (events) | event history | `TuningUpdate` |

### Agent contracts
- **Intake:** extract order_id, customer, phone, address, pincode, weight_kg, time_window, GSTIN, eway_bill_no. Validate pincode (6 digits) and phone. Return only the gaps as questions. Never invent values.
- **Planner:** capacity and time-window constrained. Output per-vehicle stop sequence, ETA per stop, total km. Must explain any order it could not assign.
- **Monitor:** every `MONITOR_INTERVAL_SEC`, compare live ETA to planned ETA. Alert if drift > 15 min, rain risk on route, or driver idle > 20 min.
- **Recovery:** pick the cheapest fix: re-sequence, reassign to nearby vehicle, or reschedule. Auto-apply if impact < threshold, else ask the dispatcher with a one-line proposal.
- **Comms:** reply in the user's language (English, Hindi, Tamil minimum). Short messages. Always include new ETA when it changes.
- **POD:** verify photo shows package at an address-like scene, check timestamp and GPS tag if present, extract recipient name from signature or note. Low confidence goes to human.
- **Feedback:** compute predicted vs actual ETA error per pincode and hour band. Write `eta_buffer_min` per pincode. Tag failure reasons. Propose prompt or constraint tweaks as a diff, never auto-edit prompts.

## Self-healing policy (core/resilience.py)
```
call -> fail -> retry x3 (exp backoff) -> fallback provider/cache -> log event -> escalate to dispatcher
```
Fallbacks: Maps API down -> haversine x 1.4 road factor. Gemini 429 -> backoff, then smaller model. Telegram down -> queue and retry, surface in UI.

## Feedback loop
`events` -> Feedback agent (nightly or on demand) -> `tuning` collection -> Planner reads `eta_buffer_min` on next plan. Show before/after ETA error in the demo.
