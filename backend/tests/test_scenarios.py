"""Day 2 acceptance: the clean case passes and each injected scenario produces an inspectable incident."""

from sqlalchemy import func, select

from app.models import Incident, PipelineRun, TransactionProcessed, TransactionRaw
from app.services import synthetic
from app.services.demo import run_scenario
from app.services.validation import reconcile

EXPECTED = synthetic.expected_summary(synthetic.generate_transactions(seed=42))


def _count(session, model, batch_id):
    return session.scalar(select(func.count()).where(model.batch_id == batch_id))


def test_clean_batch_reconciles_without_incident(session):
    outcome = run_scenario(session, "clean")

    assert outcome.incident is None
    recon = outcome.reconciliation
    assert recon.passed
    assert recon.raw_count == recon.processed_count == 1000
    assert recon.raw_sum_cents == recon.processed_sum_cents == EXPECTED["sum_cents"]
    assert [r.status for r in session.scalars(select(PipelineRun))] == ["succeeded"] * 3


def test_missing_scenario_identifies_280_ids(session):
    outcome = run_scenario(session, "missing")

    assert outcome.incident is not None
    assert outcome.incident.type == "missing_records"
    assert outcome.incident.severity == "critical"
    recon = outcome.reconciliation
    assert recon.raw_count == 1000
    assert recon.processed_count == 720
    assert len(recon.missing_ids) == 280
    assert recon.missing_ids == outcome.injected["dropped_ids"]
    assert recon.raw_sum_cents - recon.processed_sum_cents > 0

    evidence = outcome.incident.evidence
    assert evidence["reconciliation"]["missing_count"] == 280
    assert "injected_fault" not in evidence  # detection must not peek at the injected truth


def test_duplicate_scenario_rejects_duplicates_and_stores_none(session):
    outcome = run_scenario(session, "duplicate")

    assert outcome.incident is not None
    assert outcome.incident.type == "duplicate_records"
    assert outcome.incident.severity == "warning"
    assert _count(session, TransactionProcessed, outcome.batch_id) == 1000
    assert outcome.reconciliation.duplicate_ids == []
    assert outcome.incident.evidence["duplicate_attempts"] == outcome.injected["duplicated_ids"]
    assert len(outcome.incident.evidence["duplicate_attempts"]) == 40

    process_run = session.get(PipelineRun, outcome.run_ids[1])
    assert process_run.summary["rows_attempted"] == 1040
    assert process_run.summary["rows_inserted"] == 1000


def test_schema_scenario_fails_loudly_and_loads_nothing(session):
    outcome = run_scenario(session, "schema")

    assert outcome.incident is not None
    assert outcome.incident.type == "schema_mismatch"
    assert outcome.reconciliation is None
    assert _count(session, TransactionRaw, outcome.batch_id) == 0
    assert _count(session, TransactionProcessed, outcome.batch_id) == 0

    run = session.get(PipelineRun, outcome.run_ids[0])
    assert run.status == "failed"
    assert "amount_cents" in run.error and "amount" in run.error
    evidence = outcome.incident.evidence
    assert evidence["missing_fields"] == ["amount_cents"]
    assert evidence["unexpected_fields"] == ["amount"]
    assert evidence["rows_rejected"] == 1000


def test_scenarios_get_separate_batches(session):
    first = run_scenario(session, "missing")
    second = run_scenario(session, "missing")
    assert first.batch_id == "missing-001"
    assert second.batch_id == "missing-002"
    assert session.scalar(select(func.count()).select_from(Incident)) == 2
    assert reconcile(session, "missing-001").processed_count == 720
