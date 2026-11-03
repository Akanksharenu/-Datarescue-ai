# Problem statement (ticket DR-001)

## In two sentences

A retail reporting pipeline can quietly lose, duplicate, or reject transactions, so the
revenue a manager sees no longer matches what the source system recorded. Success means
the system notices the gap itself, shows exactly which records and totals disagree, and
lets an engineer approve a replay that provably brings the two back into agreement.

## The symptom we are solving

> Yesterday's raw transactions total $120k but the report displays $85k.

Before trusting either number, the following must be pinned down. Each one is a place
where two correct systems can legitimately disagree:

| Question | Our MVP answer |
|----------|----------------|
| Same date? | One reporting window per batch, labeled by `business_date` (YYYY-MM-DD). |
| Which time zone? | All timestamps are stored timezone-aware in UTC. The reporting day is a UTC day. |
| Which statuses count? | Only `completed` transactions count as revenue. `pending` and `refunded` are excluded. |
| What is revenue? | Sum of `amount_cents` over completed transactions in the window. Money is integer cents, never floats. |
| Which currency? | USD only for the MVP. |

## Personas

| Persona | Needs | In the MVP |
|---------|-------|------------|
| Data engineer | Investigate why raw and processed disagree, see the affected record IDs, trigger a safe replay. | Primary user of the API and dashboard. |
| Finance analyst | Know whether the report can be trusted and how big the gap is in dollars. | Reads incident evidence and reconciliation totals. |
| Approver | Authorize a recovery before it runs and have that approval recorded. | Records an approval on a recovery request (Day 5). |

For the MVP all three may use one local demo identity. This is **not** strong authentication
and must not be described as such.

## Functional requirements

1. **Ingest** a batch of transactions from the source into an immutable raw table.
2. **Validate** the incoming schema explicitly; a renamed required field fails loudly.
3. **Detect** missing records, duplicate records, and total mismatches with SQL checks.
4. **Inspect** an incident: run ID, batch ID, counts, totals, affected IDs, timestamps.
5. **Propose** a recovery with the planned action and expected effect.
6. **Approve** the recovery explicitly, with the approval recorded separately from execution.
7. **Reconcile** after recovery: same ID set, same count, same cents, zero duplicates.

## Non-functional requirements

- Clear errors with enough detail to act on (which field, which rows, which IDs).
- Repeatability: fixed seed, deterministic fault injection, same results every run.
- Audit history: every pipeline run and every approval is persisted and never edited.
- Readable logs and summaries, stored as JSON on the run and incident records.
- Safe retries: replaying a batch twice must not duplicate rows or revenue.

## Data flow and failure points

```
payment source  -->  load_raw  -->  transactions_raw  -->  process_batch  -->  transactions_processed  -->  revenue report
                      ^                                       ^                                              ^
                      | (3) schema mismatch:                  | (1) records dropped                          | wrong total
                      |     renamed field                     | (2) duplicate inserts                        |     shown to management
```

Failure points we reproduce on purpose:

1. **Missing records.** The transformation drops 280 of 1,000 rows. Raw has them, processed does not.
2. **Duplicate records.** The transformation sends 40 source IDs twice. The unique constraint must block them.
3. **Schema mismatch.** The source renames `amount_cents` to `amount`. Ingestion must refuse the batch.

Failure points we acknowledge but do not reproduce this week: late-arriving data, partial
batches that span two days, currency conversion, refunds applied to a prior day.
