# DataRescue AI

Enterprise data reliability and intelligent incident recovery, built as a six-day learning
project (October 27 to November 1, 2026). This is a build workbook, not a production system.
**All data in this repository is simulated.**

## The problem

A retail business receives orders and payments. Its reporting pipeline copies those
transactions from a source feed into raw tables and then into processed report tables.
That pipeline can silently drop records, insert duplicates, or break when an upstream
field is renamed. The symptom looks like this:

> Yesterday's raw transactions total $120k but the revenue report shows $85k.

DataRescue AI detects these problems with deterministic SQL checks, stores incident
evidence, explains likely causes (optionally with AI, clearly labeled), and lets an
engineer approve and verify a safe reprocessing operation.

Core flow: **detect -> investigate -> approve -> recover -> verify**.

Key rule: SQL and data checks decide whether records and totals match. AI may suggest
explanations but never decides financial correctness and never writes to the database.

## Status

| Day | Scope | Status |
|-----|-------|--------|
| 1 | Problem definition, repo, health endpoint | Done |
| 2 | Tables, seeded data, three failure scenarios, incident APIs | Done (backend) |
| 3 | Lineage, evidence, rules-based and optional AI investigation | Done (backend) |
| 4 | React/TypeScript dashboard | Done |
| 5 | Approval-gated recovery and test matrix | Done (backend) |
| 6 | Docker Compose, docs, release v0.1.0 | Done |

## Run everything with Docker (Day 6)

Prerequisite: Docker Desktop with the engine running.

```powershell
docker compose up --build
```

This starts PostgreSQL 17, the backend and the dashboard. Open http://localhost:5173 and follow
[docs/demo-script.md](docs/demo-script.md). The API is at http://localhost:8000/docs. Stop with
`Ctrl+C`, or `docker compose down -v` to also delete the database volume.

Optional settings go in a root `.env` file; see [.env.example](.env.example) for the API key and
port overrides.

## Quick start without Docker (Windows PowerShell)

Prerequisites: Python 3.11+, Git, and Node.js 20+ for the dashboard.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked, call .\.venv\Scripts\python.exe directly
python -m pip install -r requirements-dev.txt
copy .env.example .env                 # optional; defaults work without it
python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs. The health endpoint should return `{"status": "ok"}`.

By default the backend uses a SQLite file at `data/datarescue.db`, so no database server
is needed. To use PostgreSQL, set `DATABASE_URL` in `backend/.env`.

## Dashboard (Day 4)

With the backend running, start the React dashboard in a second terminal:

```powershell
cd frontend
copy .env.example .env     # optional; defaults to http://127.0.0.1:8000
npm install
npm run dev
```

Open http://localhost:5173. The pages map to the guide's Day 4 scope:

| Page | What it shows |
|------|---------------|
| Overview | Open / recovering / resolved incident counts, failed runs, proposals awaiting approval, latest incidents |
| Pipeline runs | Every stage execution with status, row counts, injected fault, and error text |
| Incidents | All detected incidents; click one for detail |
| Incident detail | Evidence snapshot, lineage graph with the failed step, investigation (rules or Claude, labeled), recovery propose / approve / reject / execute with the proof record |
| Demo control | Seed, then run `clean`, `missing`, `duplicate` or `schema` |

Every screen handles loading, empty, error and success states, and a banner on every page says
the data is simulated. The backend URL comes from `VITE_API_URL`; nothing is hard-coded.
`npm run build` type-checks and writes a static bundle to `frontend/dist/`.

## Run the demo

From the dashboard's Demo control page, the Swagger page, or any HTTP client:

1. `POST /demo/seed` resets the database and loads the clean batch of 1,000 transactions.
2. `POST /demo/run?scenario=missing` (or `duplicate`, `schema`, `clean`) executes one scenario.
3. `GET /incidents` lists detected incidents; `GET /incidents/{id}` returns the evidence.
4. `GET /pipeline-runs` shows every stage execution, including failures.

Or from the command line:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\seed_data.py            # reset + clean batch
.\.venv\Scripts\python.exe scripts\seed_data.py missing    # run one scenario
```

## Run the tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests scripts
```

Tests use an in-memory SQLite database by default, so they need no setup. To run the same suite
against PostgreSQL, start the Compose database and point the tests at it:

```powershell
docker compose up -d db
$env:TEST_DATABASE_URL = "postgresql+psycopg://datarescue:datarescue@localhost:5432/datarescue"
.\.venv\Scripts\python.exe -m pytest
```

## API

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/health` | Health check |
| POST | `/demo/seed` | Reset and load reproducible synthetic data |
| POST | `/demo/run?scenario=` | Execute `clean`, `missing`, `duplicate` or `schema` |
| GET | `/pipeline-runs` | List every stage execution |
| GET | `/incidents` | List incidents |
| GET | `/incidents/{id}` | Incident evidence and affected counts |
| POST | `/incidents/{id}/investigate?method=` | Read-only diagnosis of the evidence; `auto` uses Claude when a key is set, else rules |
| GET | `/lineage` | The dataset graph: source -> raw -> processed -> report |
| POST | `/incidents/{id}/recovery` | Create a recovery proposal (action, expected effect, preconditions) |
| GET | `/recovery`, `/recovery/{id}` | List or inspect recovery requests and their proof records |
| POST | `/recovery/{id}/approve` | Record an explicit approval (`{"approved_by": "name"}`) |
| POST | `/recovery/{id}/reject` | Reject a proposal with a reason |
| POST | `/recovery/{id}/execute` | Replay the batch (approved only), revalidate, return the proof |
| GET | `/batches/{id}/reconciliation` | Re-run deterministic checks for one batch |

## Investigation (Day 3)

Every incident carries a `lineage` block saying which step failed and which datasets
downstream of it can no longer be trusted. `POST /incidents/{id}/investigate` returns a
likely cause, confidence, what the evidence cannot establish, the evidence paths that
support the claim, and next steps for a human.

- With no `ANTHROPIC_API_KEY`, the deterministic template runs and the result says
  `method: "rules"`. The demo never pretends an LLM ran.
- With a key, Claude reads the evidence JSON and returns the same structure with
  `method: "llm"`. Every cited evidence path is checked; paths that do not exist are listed
  under `unsupported_claims` and `verified` is set to false.
- The investigator is read-only. It has no database session and cannot reach the recovery
  functions. Its output is a suggestion; reconciliation decides correctness.

Grade it against 12 labeled cases (4 injected, 8 hand-built, including ambiguous ones):

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\evaluate_investigator.py --write          # rules only
.\.venv\Scripts\python.exe scripts\evaluate_investigator.py --llm --write    # needs a key
```

Results land in [docs/investigation-eval.md](docs/investigation-eval.md).

## Recovery (Day 5)

A recovery request moves through `proposed -> approved -> executed` (or `proposed -> rejected`).
Every other transition is refused. Executing a request that is not approved is refused with
HTTP 409 **and** recorded as a failed `replay` pipeline run, so the audit trail shows the attempt.

1. `POST /incidents/{id}/recovery` builds a proposal from the live database: the batch, the
   planned action (`replay_batch`), expected inserts, and precondition checks such as "raw is
   complete" and "processed has no duplicates". Incident types with no safe automated action
   (blocked duplicates, schema failures) get HTTP 422 with the reason.
2. `POST /recovery/{id}/approve` with `{"approved_by": "name"}` records who approved and when.
   This is a demo-only identity, not authentication.
3. `POST /recovery/{id}/execute` re-runs the raw -> processed transformation with no faults.
   Inserts use `ON CONFLICT DO NOTHING`, so a second execution inserts zero rows. The response
   carries a proof record: before and after counts and cents, the approval, every revalidation
   check with its result, and each execution's run ID.

The incident becomes `resolved` only when every check passes.

### Test matrix (from the guide)

| Case | Expected result | Test |
|------|-----------------|------|
| Clean 1,000 rows | No incident; raw and processed reconcile | `test_scenarios.py::test_clean_batch_reconciles_without_incident` |
| 280 dropped | Missing-record incident identifies 280 IDs | `test_scenarios.py::test_missing_scenario_identifies_280_ids` |
| Duplicate attempt | Warning; no duplicate rows stored | `test_scenarios.py::test_duplicate_scenario_rejects_duplicates_and_stores_none` |
| Renamed required field | Schema failure, useful error, nothing loaded | `test_scenarios.py::test_schema_scenario_fails_loudly_and_loads_nothing` |
| Approved replay | Batch returns to reconciled state | `test_recovery.py::test_approved_replay_returns_batch_to_reconciled_state` |
| Repeated approved replay | No extra records or revenue | `test_recovery.py::test_repeated_approved_replay_adds_no_records_or_revenue` |
| Unapproved replay | Rejected and recorded | `test_recovery.py::test_unapproved_replay_is_rejected_and_recorded` |
| AI unavailable | Rules-based investigation remains usable | `test_investigation.py::test_investigate_without_key_uses_rules_and_says_so` |

## Screenshots

Not captured yet. Run the stack with Docker and follow [docs/demo-script.md](docs/demo-script.md)
to see the Overview page, an incident with its lineage and investigation, and the recovery proof.

## Failure scenarios

| Scenario | What is injected | What the system records |
|----------|------------------|-------------------------|
| `missing` | Transformation drops 280 of 1,000 records | Critical `missing_records` incident listing the 280 IDs and the cents shortfall |
| `duplicate` | Transformation re-sends 40 source IDs | Warning `duplicate_records` incident; the unique constraint rejects all 40, zero duplicates stored |
| `schema` | Source renames `amount_cents` to `amount` | Failed `load_raw` run, nothing loaded, critical `schema_mismatch` incident naming the fields |
| `clean` | Nothing | Raw and processed reconcile; no incident |

## Project layout

```
backend/
  app/
    api/routes.py          HTTP endpoints
    services/synthetic.py  deterministic data + fault injectors
    services/pipeline.py   load_raw and process_batch stages
    services/validation.py reconciliation checks (deterministic)
    services/incidents.py  evidence snapshots -> incidents
    services/lineage.py    dataset graph and impact
    services/investigation.py  rules diagnoser + optional Claude investigator
    services/recovery.py   propose / approve / execute / proof
    services/demo.py       scenario runner
    models.py              SQLAlchemy tables
    schemas.py             Pydantic contracts
  scripts/seed_data.py     CLI seeding
  scripts/evaluate_investigator.py  grade diagnoses against labeled cases
  tests/                   pytest suite
docs/                      problem statement, architecture, demo script, decision and bug logs
data/                      local SQLite file (ignored by Git)
docker-compose.yml         PostgreSQL + backend + dashboard (Day 6)
backend/Dockerfile         python:3.13-slim + uvicorn
frontend/Dockerfile        node build stage -> nginx static serve
frontend/
  src/api/types.ts         TypeScript mirrors of schemas.py
  src/api/client.ts        one typed function per backend route
  src/hooks/               useAsync (loading/empty/error/success), hash router
  src/components/          badges, states, lineage graph
  src/pages/               Overview, PipelineRuns, Incidents, IncidentDetail, DemoControl
```

See [docs/problem-statement.md](docs/problem-statement.md) and
[docs/architecture.md](docs/architecture.md) for the design.
