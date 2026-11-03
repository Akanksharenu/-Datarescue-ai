# Decision log

Add two or three genuine observations at the end of each day.

## 2026-10-27 (Day 1)

**Rebuilt the backend to the workbook's contract instead of extending the earlier prototype.**
An earlier draft modeled three sources with 30 daily batches and `stg_*` staging tables. The
workbook's tests, routes and demo script are written against `transactions_raw`,
`transactions_processed`, `pipeline_runs`, `incidents` and `recovery_requests` with one batch of
1,000 rows. Rewriting now costs a few hours; carrying two designs through six days would cost more.
The old files are kept in `backend/_legacy_week1/` for reference.

**SQLite by default, PostgreSQL by configuration.** Docker Desktop and PostgreSQL are not installed
on the development machine yet. Rather than block Day 1 on installing them, the app defaults to a
local SQLite file and switches to PostgreSQL through `DATABASE_URL`. The only dialect-specific code
is the `INSERT ... ON CONFLICT` import, which is selected at runtime. Day 6 will add Docker Compose
and run the suite against PostgreSQL before release.

**Uniqueness scoped to `(batch_id, source_id)`, not `source_id` alone.** Every demo scenario replays
the same 1,000 source IDs into its own batch so that scenarios can be run side by side. A global
unique constraint would make the second scenario fail for the wrong reason.

**Injected faults are recorded on the run, never in the incident evidence.** Detection has to work
from the data alone; otherwise the demo would be cheating. The label is kept on
`pipeline_runs.summary.injected_fault` so Day 3 can measure diagnosis accuracy against ground truth.

## 2026-10-27 (Day 3, started the same day)

**The investigator gets a dict, not a database session.** Both diagnosers take the incident's
`evidence` JSON and nothing else. There is no code path from investigation to the pipeline or
recovery modules, which is how "AI must not execute database writes" is enforced structurally
rather than by instruction alone.

**Every LLM claim is checked against the evidence before it is shown.** The model must cite
dotted paths into the evidence JSON. Paths that do not resolve are listed as unsupported claims
and the result is marked unverified. A diagnosis that points at data which does not exist is the
most likely failure mode, so it is the one we check mechanically.

**Rules and LLM return the identical structure.** The frontend and the eval script never need to
know which ran; `method` says so. That also makes the fallback honest: when the key is missing or
the API fails, the response says `method: "rules"` plus a `fallback_reason`.

**The rules score is a regression check, not a measurement.** The templates were written against
the same scenarios they are graded on, so 12/12 is expected and proves only that nothing regressed.
The LLM column in `docs/investigation-eval.md` is the only independent number, and it needs a key.

## 2026-10-27 (Day 5, built before Day 4 because Node.js is not installed yet)

**Replay is the normal process stage with no faults, not a separate code path.** `execute_recovery`
calls the same `process_batch` the pipeline uses, tagged `stage="replay"`. Because that stage already
upserts with `ON CONFLICT DO NOTHING`, idempotency is inherited rather than re-implemented. The test
for "repeated approved replay adds nothing" passes for the same reason the duplicate scenario does.

**A refused execution is still recorded.** The guide's matrix says an unapproved replay must be
"rejected and recorded". Refusing with HTTP 409 alone leaves no trace, so the refusal also writes a
failed `replay` pipeline run and appends to `refused_attempts` on the request. The audit trail shows
that someone tried.

**Approval is a name, and the docs say so.** `approved_by` is a free-text string. Day 5 is about the
workflow shape (separate approval and execution records, state machine, proof), not identity. Calling
this authentication would be the kind of misleading claim the guide warns against.

**Not every incident type gets a recovery action.** Blocked duplicates need nothing. A schema failure
needs a corrected extract, not a replay. Incomplete raw would just reproduce the gap. Each unsupported
type returns 422 with that reason instead of a generic "unsupported".

**Duplicates are blocked by the database, not by Python.** The process stage really attempts the
40 duplicate inserts; `ON CONFLICT DO NOTHING` plus the unique constraint rejects them, and the
rejected count is what goes into the incident. This is the behavior a replay on Day 5 depends on.

## 2026-10-29 (Day 4)

**No UI framework beyond React, and a hash router instead of React Router.** The dashboard has
five screens and one entity to drill into. A twenty-line `useHashRoute` hook covers that, keeps
`npm install` to two runtime packages, and means the built bundle can be served from any static
host on Day 6 without rewrite rules. If the app grows real nested routes, swap it for React Router.

**The TypeScript types are hand-copied from `schemas.py`, not generated.** Generating them from
the OpenAPI document is the better long-term answer, but it adds a build step and a tool to learn
on a day with four screens to build. The file header says where the source of truth is; a field
rename on the backend now fails the `tsc` build instead of silently rendering `undefined`.

**Errors carry the backend's words.** The API client throws `ApiError(status, "409: Recovery
request 3 is not approved (status: proposed)")`. The recovery module already writes precise
refusal messages; the UI's job is to show them, not translate them. The "Try execute without
approval" button exists so the demo can show a refusal being recorded, which is a guide test case.

**Money formatting builds the string from integer cents.** `cents(25505253)` splits into dollars
and remainder with integer division, so the display can never drift from the stored value. The
dashboard never does arithmetic on amounts except the shortfall, which is one integer subtraction.

**The AI badge is always visible.** Every investigation card shows `rules` or `LLM: <model>`, the
confidence, whether its evidence paths were verified, and the backend's disclaimer. A reader
should never have to wonder whether a sentence was written by a template or a model.

## 2026-10-29 (Day 6)

**Three containers, not two.** The guide asks for PostgreSQL plus backend. The dashboard was
added as a third service because a reviewer who runs one command should see the product, not
a Swagger page. It costs one more Dockerfile and nothing at runtime.

**The API URL is baked into the frontend image at build time.** Vite inlines `VITE_API_URL`
during `npm run build`; there is no runtime substitution without extra tooling. The Compose
file passes it as a build argument so a different host port is one variable change. The
trade-off is that changing the backend address means rebuilding the frontend image.

**Tests run against PostgreSQL through one environment variable.** `TEST_DATABASE_URL`
switches the shared `engine` fixture from in-memory SQLite to any SQLAlchemy URL and drops and
recreates the schema per test. No test file changed. Running the full suite on PostgreSQL
before tagging is what turns "it works on SQLite" into a release claim.

**The Docker install took longer than the Docker work.** The machine's system PATH had been
overwritten by an earlier install and WSL was missing, so `wsl`, `reg` and `where` were all
"not recognized". Fixing the PATH and installing WSL 2 unblocked Docker Desktop. Recorded in the
bug log so the next person does not spend an hour on an installer that says "up to date".
