"""Turn pipeline results into persisted incidents with an evidence snapshot."""

from dataclasses import asdict

from sqlalchemy.orm import Session

from app.models import Batch, Incident, PipelineRun
from app.services.lineage import impact
from app.services.pipeline import ProcessSummary, SchemaMismatchError
from app.services.validation import Reconciliation

# First matching finding decides the incident type; the rest are kept as evidence.
PRIMARY_ORDER = (
    "incomplete_raw_load",
    "missing_records",
    "unexpected_records",
    "duplicate_records",
    "total_mismatch",
    "window_mismatch",
    "status_inconsistent",
)


def _base_evidence(batch: Batch, run: PipelineRun | None) -> dict:
    return {
        "simulated": True,
        "batch_id": batch.id,
        "business_date": batch.business_date,
        "run_id": run.id if run else None,
        "stage": run.stage if run else None,
        "expected_count": batch.expected_count,
        "expected_sum_cents": batch.expected_sum_cents,
    }


def open_incident_from_schema_error(
    session: Session, batch: Batch, run: PipelineRun, exc: SchemaMismatchError
) -> Incident:
    missing = sorted({e["field"] for e in exc.errors if e["kind"] == "missing"})
    extra = sorted({e["field"] for e in exc.errors if e["kind"] == "extra_forbidden"})
    evidence = _base_evidence(batch, run) | {
        "rows_received": run.summary.get("rows_received"),
        "rows_loaded": 0,
        "rows_rejected": exc.rows_rejected,
        "missing_fields": missing,
        "unexpected_fields": extra,
        "sample_errors": exc.errors[:5],
        "error": str(exc),
        "lineage": impact("schema_mismatch"),
    }
    incident = Incident(
        batch_id=batch.id, run_id=run.id, type="schema_mismatch", severity="critical", evidence=evidence
    )
    session.add(incident)
    session.commit()
    return incident


def open_incident_from_reconciliation(
    session: Session,
    batch: Batch,
    run: PipelineRun,
    recon: Reconciliation,
    process_summary: ProcessSummary | None,
) -> Incident | None:
    """Create one incident per batch when reconciliation or the process stage reports a problem."""
    findings = {f.code: f for f in recon.findings}
    primary = next((code for code in PRIMARY_ORDER if code in findings), None)
    rejected_dups = process_summary.duplicates_rejected if process_summary else []

    if primary is None and not rejected_dups:
        return None

    evidence = _base_evidence(batch, run) | {
        "reconciliation": recon.to_dict(),
        "process_summary": asdict(process_summary) if process_summary else None,
    }

    if primary is None:
        # Duplicates were attempted and blocked by the unique constraint: tables are intact.
        incident_type, severity = "duplicate_records", "warning"
        evidence["duplicate_attempts"] = rejected_dups
        evidence["duplicates_stored"] = recon.duplicate_ids
        evidence["lineage"] = impact(incident_type, duplicates_blocked=True)
    else:
        incident_type, severity = primary, findings[primary].severity
        evidence["lineage"] = impact(incident_type)

    incident = Incident(
        batch_id=batch.id, run_id=run.id, type=incident_type, severity=severity, evidence=evidence
    )
    session.add(incident)
    session.commit()
    return incident
