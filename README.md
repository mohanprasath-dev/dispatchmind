# DispatchMind: AI Dispatch Co-pilot for Logistics Handlers

Multi-agent system that automates order intake, route planning, live monitoring, exception recovery, customer messaging and proof of delivery for small and mid fleet operators.

## Competition criteria map
| Criterion | Implementation |
|---|---|
| Multi-modal agents | Intake (invoice, e-way bill), POD (delivery photo) |
| Conversation agents | Comms agent, dispatcher chat |
| API calls | Google Maps Routes, Open-Meteo, Telegram, Gemini |
| MCP integration | `mcp_servers/` (orders, maps, weather, notify, docs) |
| Feedback loop | Feedback agent tunes per-pincode ETA buffers |
| Self-healing | `core/resilience.py` retry, fallback, escalate; Recovery agent |

## Architecture
```
Chat UI / Telegram -> Orchestrator (ADK)
  Intake | Planner | Monitor | Recovery | Comms | POD | Feedback
                     MCP tool layer
  orders | maps | weather | notify | docs
        Firestore, Maps, Open-Meteo, Telegram, Cloud Storage
```

## Prerequisites
- Python 3.11+, git
- Gemini API key (aistudio.google.com)
- Optional for full mode: Google Cloud project, Maps key, Telegram bot (see SECRETS_AND_APIS.md)

## Quick start (demo mode, 5 minutes)
```
git clone <repo-url> && cd dispatchmind
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # set GOOGLE_API_KEY, keep DEMO_MODE=true
python -m core.seed
uvicorn app.main:app --reload
```
Open http://localhost:8000

## Demo flow
1. Upload `data/sample_orders/invoice_01.jpg`. Agent returns the order or asks one question.
2. Click "Plan day". Routes and ETAs appear.
3. In "Break something", click "Vehicle breakdown". Watch Monitor, Recovery and Comms act in the event log.
4. Send a delivery photo as the driver. Order closes with POD.
5. Click "Run feedback". See ETA error before and after.

## ADK dev UI
```
adk web agents
```

## Full mode
Set all variables in `.env` (see `.env.example`), set `DEMO_MODE=false`, then run the same command.

## Tests
```
pytest -q
```

## Deploy to Cloud Run
```
gcloud run deploy dispatchmind --source . --region asia-south1 --allow-unauthenticated \
  --set-env-vars DEMO_MODE=false \
  --set-secrets GOOGLE_API_KEY=gemini-key:latest,GOOGLE_MAPS_API_KEY=maps-key:latest,TELEGRAM_BOT_TOKEN=tg-token:latest
```

## Troubleshooting
| Symptom | Fix |
|---|---|
| 429 from Gemini | Fallback model engages automatically; wait or lower `MONITOR_INTERVAL_SEC` |
| Maps errors | App falls back to haversine estimates and logs an event |
| No Telegram messages | Messages print to console and the UI log in demo mode |
