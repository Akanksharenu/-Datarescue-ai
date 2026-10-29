# Architecture overview

## System boundaries

```
+-------------------+      +------------------+      +--------------------------+
| Synthetic source  | ---> | Ingestion        | ---> | PostgreSQL / SQLite      |
| (seeded, 1,000    |      | load_raw()       |      |  transactions_raw        |
|  transactions)    |      | Pydantic contract|      |  transactions_processed  |
+-------------------+      +------------------+      |  pipeline_runs           |
                                                     |  incidents               |
+-------------------+      +------------------+      |  recovery_requests       |
| Transformation    | ---> | Validation       | ---> |  batches                 |
| process_batch()   |      | reconcile()      |      +--------------------------+
| (faults injected  |      | SQL checks only  |                  |
|  here on purpose) |      +------------------+                  v
+-------------------+                                 +--------------------------+
                                                      | FastAPI                  |
+-------------------+                                 |  /demo/* /incidents      |
| AI investigator   | <--- read-only evidence ------- |  /pipeline-runs          |
| (Day 3, optional, |                                 +--------------------------+
|  rules fallback)  |                                              |
+-------------------+                                              v
                                                      +--------------------------+
+-------------------+                                 | React dashboard (Day 4)  |
| Recovery (Day 5)  | <--- explicit approval -------- |                          |
| approval-gated    |                                 +--------------------------+
| idempotent replay |
+-------------------+
```

The AI investigator only ever reads incident evidence. It cannot call the pipeline, the
recovery functions, or the database.

## Pipeline stages

Each stage writes one `pipeline_runs` row that is never edited after it finishes.

| Stage | Input | Output | Fails when |
|-------|-------|--------|------------|
| `load_raw` | incoming rows | `transactions_raw` | any row violates the `IncomingTransaction` contract (nothing is loaded) |
| `process` | raw rows for a batch | `transactions_processed` | database error |
| `reconcile` | raw + processed + batch expectations | findings list | never fails; findings become an incident |

Duplicates are handled by the database: processing uses `INSERT ... ON CONFLICT DO NOTHING`
against the `(batch_id, source_id)` unique constraint, and the number of rejected rows is
recorded on the run. Python never has to "remember" what was already inserted.

## Database contract

| Table | Key fields | Why it exists |
|-------|------------|---------------|
| `batches` | id, scenario, business_date, expected_count, expected_sum_cents | What the source promised for one window |
| `transactions_raw` | batch_id + source_id (unique), amount_cents, status, occurred_at | Immutable copy of what arrived |
| `transactions_processed` | batch_id + source_id (unique), amount_cents, processed_at | Report-ready rows; uniqueness blocks replays |
| `pipeline_runs` | batch_id, stage, status, started_at, finished_at, error, summary JSON | Every execution and its outcome |
| `incidents` | batch_id, run_id, type, severity, status, evidence JSON | Immutable evidence snapshot at detection time |
| `recovery_requests` | incident_id, action, status, proposal, approved_by, approved_at, result | Approval and execution recorded separately |

Money is integer cents. Timestamps are timezone-aware UTC. Uniqueness is scoped to a batch
because every demo scenario replays the same 1,000 source IDs into its own batch.

## Reconciliation findings

`reconcile()` compares three things for one batch and emits zero or more findings:

| Code | Severity | Meaning |
|------|----------|---------|
| `incomplete_raw_load` | critical | raw count differs from what the source promised |
| `missing_records` | critical | raw IDs absent from processed |
| `unexpected_records` | critical | processed IDs absent from raw |
| `duplicate_records` | critical | a source ID stored more than once in processed |
| `total_mismatch` | critical | sum of cents differs between raw and processed |
| `window_mismatch` | warning | processed rows fall outside the batch's business date |
| `status_inconsistent` | warning | processed rows that are not `completed` |

The first finding in that order becomes the incident type. When the process stage reports
rejected duplicate attempts but reconciliation is clean, a `duplicate_records` incident is
opened at `warning` severity: the attack was real, the tables stayed intact.

## What the incident evidence contains

- batch ID, run ID, stage, business date
- expected count and sum from the source
- the full reconciliation result (counts, sums, missing/unexpected/duplicate IDs, findings)
- the process-stage summary (rows attempted, inserted, duplicates rejected, rows dropped)
- for schema failures: rows received and rejected, missing and unexpected field names, sample errors

The injected fault is recorded on the **run** (`summary.injected_fault`), not on the incident.
Detection must work from the data alone; the injected label exists so Day 3 can grade diagnoses.

## Local development

- Default database: SQLite file at `data/datarescue.db` (no server needed).
- PostgreSQL: set `DATABASE_URL=postgresql+psycopg://...` in `backend/.env`. Day 6 adds Docker Compose.
- Tests: in-memory SQLite, one fresh database per test.
- Schema setup: `Base.metadata.create_all` on startup; `POST /demo/seed` drops and recreates.
