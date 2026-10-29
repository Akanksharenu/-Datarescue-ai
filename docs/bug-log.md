# Bug log

For each entry record: exact error text, environment, reproduction steps, likely cause, fix.

## 2026-10-27 (Day 1)

**Environment:** Windows 11, Python 3.13.7, SQLAlchemy 2.1.6, FastAPI 0.162.0, SQLite.

**1. PowerShell could not find `node`, `npm` or `docker`.**
Error: `The term 'node' is not recognized as the name of a cmdlet...`
Cause: not installed yet. Impact: none until Day 4 (Node) and Day 6 (Docker).
Fix: deferred; install Node.js LTS before Day 4 and Docker Desktop before Day 6.

**2. No PostgreSQL service on port 5432.**
Check: `Test-NetConnection 127.0.0.1 -Port 5432` returned False.
Fix: backend defaults to SQLite (see decision log). PostgreSQL via `DATABASE_URL` when available.

**3. Ruff flagged `Depends(...)` in argument defaults (B008).**
This is the standard FastAPI idiom, not a bug. Fix: rule B008 ignored in `pyproject.toml`.

**4. pytest refused to start after editing `pyproject.toml` from PowerShell.**
Error: `ERROR: ...\pyproject.toml: Invalid statement (at line 1, column 1)`
Repro: `Set-Content pyproject.toml -Encoding utf8` in Windows PowerShell 5.1, then `python -m pytest`.
Cause: PowerShell 5.1 writes UTF-8 *with* a byte-order mark (bytes `EF BB BF`); the TOML parser
treats it as an invalid first character. Ruff tolerated it, pytest did not, which made it look
like a pytest problem. Confirmed with `od -c pyproject.toml | head -1`.
Fix: stripped the three bytes (`tail -c +4`). Lesson: edit config files with an editor or a
tool that writes UTF-8 without BOM; verify with a byte dump when a parser blames line 1, column 1.

**5. Refused recovery attempts were saved with `run_id: null` and erased by a later execution.**
Found: driving the Day 4 dashboard flow over HTTP. `GET /recovery/1` after a refused execute
showed `"run_id": null`; after the approved execute, `refused_attempts` was gone entirely.
Why the test missed it: `test_unapproved_replay_is_rejected_and_recorded` reads the same session
object that did the write, so it saw the in-memory list, never the database row.
Cause 1: `_record_refusal` appended to the existing list and mutated the entry in place. The old
and new JSON values then compared equal, so SQLAlchemy skipped the UPDATE on the second commit.
Cause 2: `execute_recovery` replaced `request.result` with the proof and did not carry the earlier
refusals forward.
Fix: `session.flush()` to get the run id, build a brand-new list and dict, one commit; the proof
now copies `refused_attempts` into itself. The API test now reads the record back over HTTP and
asserts the run id is an integer and that the proof still lists the refusal.
Lesson: a test that checks persistence must read through a fresh session or over the API.
