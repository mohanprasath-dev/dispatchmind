# Execution Plan (10 days, 3 people)

## Roles
- **A: Agents and ADK:** P3, P4, P5, P6, P7 agent logic, orchestrator
- **B: Backend and MCP:** P0, P1, P2, store, Maps, deploy
- **C: UI, docs, demo:** P8 UI, README, sample data, demo video

## Schedule
| Day | A | B | C |
|---|---|---|---|
| 1 | ADK skeleton | P0 scaffold, repo, GCP, keys | Collect 5 sample invoices, UI wireframe |
| 2 | Intake prompt | P1 resilience, P2 orders and maps MCP | Seed data, chat UI shell |
| 3 | P3 Intake | P2 weather, notify, docs MCP | Upload UI |
| 4 | P4 Planner | Planner distance matrix glue | Route table view |
| 5 | P5 Monitor | Failure injection endpoints | Event log panel |
| 6 | P5 Recovery | Resilience tests | Break-something panel |
| 7 | P6 Comms, POD | Telegram wiring | POD upload UI |
| 8 | P7 Feedback | Metrics endpoint | Before/after card |
| 9 | Orchestrator polish | Cloud Run deploy | README, fresh clone test |
| 10 | Bug fixes | Bug fixes | Record demo, submit |

## Cut order if late
1. Hindi and Tamil
2. Map view (keep table)
3. Telegram (keep console channel)
4. End-of-day report

Never cut: Intake, Planner, Recovery, MCP, Feedback, resilience, README.

## Demo script (3 minutes)
1. 0:00 Problem in one line
2. 0:20 Upload invoice, order appears
3. 0:50 Plan day
4. 1:20 Break a vehicle, show auto recovery and customer message
5. 2:00 Driver POD closes order
6. 2:20 Feedback run, ETA error drops
7. 2:40 Architecture slide, criteria map
8. 2:55 Pricing line

## Submission checklist
- [ ] Public GitHub repo
- [ ] README runs from fresh clone
- [ ] .env.example present, no secrets committed
- [ ] AGENTS.md and PRD.md in root
- [ ] Cloud Run link in README
- [ ] Demo video link in README
- [ ] Submission form filed early (first come first served)
