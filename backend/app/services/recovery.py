"""Approval-gated recovery (ticket DR-010): propose -> approve -> execute -> prove.

State machine for a RecoveryRequest:

    proposed --approve--> approved --execute--> executed (re-executable, idempotent)
    proposed --reject---> rejected

Anything else is an invalid transition and is refused. An execute attempt on a request that
is not approved is refused AND recorded as a failed pipeline run, so the audit trail shows it.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Batch, Incident, PipelineRun, RecoveryRequest, utcnow
from app.services.pipeline import process_batch
from app.services.validation import reconcile

REPLAY_BATCH = "replay_batch"

# Which incident types have a supported recovery action, and why the others do not.
SUPPORTED_ACTIONS: dict[str, str] = {
    "missing_records": REPLAY_BATCH,
    "total_mismatch": REPLAY_BATCH,
}
UNSUPPORTED_REASON: dict[str, str] = {
    "duplicate_records": "duplicates were blocked by the unique constraint; processed data is intact "
    "and there is nothing to replay",
    "schema_mismatch": "nothing was loaded; recovery needs a corrected extract from the source, "
    "not a replay of this batch",
    "incomplete_raw_load": "raw is missing records; replaying raw into processed would reproduce the gap",
    "unexpected_records": "removing rows is not a supported automated action; needs manual review",
}


class RecoveryError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Check:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


# --- Propose ------------------------------------------------------------------


def propose_recovery(session: Session, incident: Incident) -> RecoveryRequest:
    """Build a proposal from the current database state. Raises RecoveryError if unsupported."""
    if incident.status == "resolved":
        raise RecoveryError(f"Incident {incident.id} is already resolved")
    action = SUPPORTED_ACTIONS.get(incident.type)
    if action is None:
        reason = UNSUPPORTED_REASON.get(incident.type, "no automated recovery is defined for this type")
        raise RecoveryError(f"No supported recovery for incident type {incident.type!r}: {reason}", 422)

    existing = session.scalars(
        select(RecoveryRequest).where(
            RecoveryRequest.incident_id == incident.id, RecoveryRequest.status.in_(["proposed", "approved"])
        )
    ).first()
    if existing is not None:
        raise RecoveryError(f"Recovery request {existing.id} is already {existing.status} for this incident")

    batch = session.get(Batch, incident.batch_id)
    before = reconcile(session, batch.id)
    preconditions = _preconditions(batch, before, incident)

    proposal = {
        "simulated": True,
        "batch_id": batch.id,
        "incident_type": incident.type,
        "action": action,
        "description": (
            "Re-run the raw -> processed transformation for this batch with no faults. "
            "Inserts use ON CONFLICT DO NOTHING on (batch_id, source_id), so rows already present "
            "are untouched and a second run inserts nothing."
        ),
        "expected_inserts": len(before.missing_ids),
        "expected_updates": 0,
        "expected_processed_count_after": before.raw_count,
        "expected_processed_sum_cents_after": before.raw_sum_cents,
        "before": before.to_dict(),
        "preconditions": [c.to_dict() for c in preconditions],
        "preconditions_met": all(c.passed for c in preconditions),
    }
    request = RecoveryRequest(incident_id=incident.id, action=action, status="proposed", proposal=proposal)
    session.add(request)
    session.commit()
    return request


def _preconditions(batch: Batch, before, incident: Incident) -> list[Check]:
    return [
        Check(
            "raw_is_complete",
            before.raw_count == batch.expected_count,
            f"raw has {before.raw_count} of {batch.expected_count} promised records",
        ),
        Check(
            "raw_has_no_duplicates",
            True,
            "unique constraint on (batch_id, source_id) enforced by the database",
        ),
        Check(
            "processed_has_no_foreign_rows",
            not before.unexpected_ids,
            f"{len(before.unexpected_ids)} processed rows without a raw counterpart",
        ),
        Check(
            "processed_has_no_duplicates",
            not before.duplicate_ids,
            f"{len(before.duplicate_ids)} duplicate source IDs in processed",
        ),
        Check("incident_is_open", incident.status != "resolved", f"incident status is {incident.status}"),
    ]


# --- Approve / reject ---------------------------------------------------------


def approve_recovery(session: Session, request: RecoveryRequest, approved_by: str) -> RecoveryRequest:
    """Record an explicit approval. Demo-only identity: a name, not an authenticated principal."""
    if request.status != "proposed":
        raise RecoveryError(f"Cannot approve a request in status {request.status!r}; must be 'proposed'")
    if not approved_by.strip():
        raise RecoveryError("approved_by must not be empty", 422)
    if not request.proposal.get("preconditions_met", False):
        raise RecoveryError("Preconditions are not met; the proposal cannot be approved")
    request.status = "approved"
    request.approved_by = approved_by.strip()
    request.approved_at = utcnow()
    incident = session.get(Incident, request.incident_id)
    incident.status = "recovering"
    session.commit()
    return request


def reject_recovery(
    session: Session, request: RecoveryRequest, rejected_by: str, reason: str
) -> RecoveryRequest:
    if request.status != "proposed":
        raise RecoveryError(f"Cannot reject a request in status {request.status!r}; must be 'proposed'")
    request.status = "rejected"
    request.result = {
        "rejected_by": rejected_by.strip() or "unknown",
        "reason": reason,
        "at": utcnow().isoformat(),
    }
    session.commit()
    return request


# --- Execute ------------------------------------------------------------------


def execute_recovery(session: Session, request: RecoveryRequest) -> RecoveryRequest:
    """Replay the batch inside one transaction, revalidate, and write a proof record.

    Refuses (and records) execution unless the request is approved or already executed.
    Re-executing an executed request is allowed and must change nothing.
    """
    incident = session.get(Incident, request.incident_id)
    batch = session.get(Batch, incident.batch_id)

    if request.status not in ("approved", "executed"):
        _record_refusal(
            session, batch, request, f"recovery request {request.id} is {request.status}, not approved"
        )
        raise RecoveryError(f"Recovery request {request.id} is not approved (status: {request.status})")
    if request.action != REPLAY_BATCH:
        _record_refusal(session, batch, request, f"unsupported action {request.action!r}")
        raise RecoveryError(f"Unsupported recovery action {request.action!r}", 422)

    before = reconcile(session, batch.id)
    run, summary = process_batch(session, batch, stage="replay")  # commits on success, rolls back on error
    after = reconcile(session, batch.id)

    checks = [
        Check(
            "source_id_set_matches",
            not after.missing_ids and not after.unexpected_ids,
            f"{len(after.missing_ids)} missing, {len(after.unexpected_ids)} unexpected",
        ),
        Check(
            "count_matches",
            after.raw_count == after.processed_count,
            f"raw {after.raw_count}, processed {after.processed_count}",
        ),
        Check(
            "amount_totals_match",
            after.raw_sum_cents == after.processed_sum_cents,
            f"raw {after.raw_sum_cents} cents, processed {after.processed_sum_cents} cents",
        ),
        Check("no_duplicates", not after.duplicate_ids, f"{len(after.duplicate_ids)} duplicate source IDs"),
        Check(
            "reporting_window_consistent",
            not any(f.code == "window_mismatch" for f in after.findings),
            f"business date {after.business_date}",
        ),
        Check("reconciliation_passed", after.passed, f"{len(after.findings)} findings remain"),
    ]
    passed = all(c.passed for c in checks)

    executions = list((request.result or {}).get("executions", []))
    executions.append(
        {
            "run_id": run.id,
            "at": utcnow().isoformat(),
            "rows_attempted": summary.rows_attempted,
            "rows_inserted": summary.rows_inserted,
            "processed_before": before.processed_count,
            "processed_after": after.processed_count,
        }
    )
    proof = {
        "simulated": True,
        "status": "verified" if passed else "failed",
        "batch_id": batch.id,
        "action": request.action,
        "approval": {"approved_by": request.approved_by, "approved_at": _iso(request.approved_at)},
        "before": {
            "processed_count": before.processed_count,
            "processed_sum_cents": before.processed_sum_cents,
            "missing_count": len(before.missing_ids),
        },
        "after": {
            "processed_count": after.processed_count,
            "processed_sum_cents": after.processed_sum_cents,
            "missing_count": len(after.missing_ids),
        },
        "rows_inserted_this_run": summary.rows_inserted,
        "checks": [c.to_dict() for c in checks],
        "executions": executions,
        # Refusals that happened before approval stay on the record; the proof must not erase them.
        "refused_attempts": list((request.result or {}).get("refused_attempts", [])),
        "verified_at": utcnow().isoformat(),
    }

    request.result = proof
    request.executed_at = utcnow()
    request.status = "executed" if passed else "failed"
    incident.status = "resolved" if passed else "open"
    session.commit()
    return request


def _record_refusal(session: Session, batch: Batch, request: RecoveryRequest, reason: str) -> None:
    """A refused execution is still an event: write a failed run so the audit trail shows it."""
    run = PipelineRun(
        batch_id=batch.id,
        scenario=batch.scenario,
        stage="replay",
        status="failed",
        error=f"refused: {reason}",
        summary={"recovery_request_id": request.id, "refused": True},
    )
    run.finished_at = run.started_at = utcnow()
    session.add(run)
    session.flush()  # assigns run.id without ending the transaction
    # Build a brand-new list and dict. Mutating the old ones in place makes SQLAlchemy's JSON
    # change detection see "no net change" and skip the UPDATE (found via the dashboard on Day 4).
    attempts = [
        *(request.result or {}).get("refused_attempts", []),
        {"at": utcnow().isoformat(), "reason": reason, "run_id": run.id},
    ]
    request.result = {**(request.result or {}), "refused_attempts": attempts}
    session.commit()


def _iso(value) -> str | None:
    return value.isoformat() if value else None
