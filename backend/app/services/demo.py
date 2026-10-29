"""Demo runner: seed reproducible data and execute one of the controlled failure scenarios.

Everything produced here is simulated. It exists so the detect -> investigate -> approve ->
recover -> verify flow can be demonstrated and tested without real customer data.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import Base, Batch, Incident, PipelineRun
from app.services import synthetic
from app.services.incidents import open_incident_from_reconciliation, open_incident_from_schema_error
from app.services.pipeline import SchemaMismatchError, load_raw, process_batch
from app.services.validation import Reconciliation, reconcile

SCENARIOS = ("clean", "missing", "duplicate", "schema")


@dataclass
class ScenarioOutcome:
    scenario: str
    batch_id: str
    run_ids: list[int]
    incident: Incident | None
    reconciliation: Reconciliation | None
    injected: dict

    def to_dict(self) -> dict:
        return {
            "simulated": True,
            "scenario": self.scenario,
            "batch_id": self.batch_id,
            "run_ids": self.run_ids,
            "incident_id": self.incident.id if self.incident else None,
            "reconciliation": self.reconciliation.to_dict() if self.reconciliation else None,
        }


def reset_schema(engine: Engine) -> None:
    """Drop and recreate every table. Repeatable schema setup for the demo."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _next_batch_id(session: Session, scenario: str) -> str:
    n = session.scalar(select(func.count()).select_from(Batch).where(Batch.scenario == scenario)) or 0
    return f"{scenario}-{n + 1:03d}"


def run_scenario(session: Session, scenario: str, seed: int = 42) -> ScenarioOutcome:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario {scenario!r}; expected one of {SCENARIOS}")

    rows = synthetic.generate_transactions(seed=seed)
    expected = synthetic.expected_summary(rows)
    batch = Batch(
        id=_next_batch_id(session, scenario),
        scenario=scenario,
        business_date=synthetic.BUSINESS_DATE.isoformat(),
        expected_count=expected["count"],
        expected_sum_cents=expected["sum_cents"],
    )
    session.add(batch)
    session.flush()

    injected: dict = {"scenario": scenario}
    run_ids: list[int] = []

    incoming = rows
    if scenario == "schema":
        incoming = synthetic.rename_field(rows)
        injected["renamed_field"] = {"from": synthetic.RENAMED_FIELD[0], "to": synthetic.RENAMED_FIELD[1]}

    try:
        load_run, _ = load_raw(session, batch, incoming)
    except SchemaMismatchError as exc:
        load_run = session.scalars(
            select(PipelineRun).where(PipelineRun.batch_id == batch.id).order_by(PipelineRun.id.desc())
        ).first()
        incident = open_incident_from_schema_error(session, batch, load_run, exc)
        _stamp_injected(session, load_run, injected)
        return ScenarioOutcome(scenario, batch.id, [load_run.id], incident, None, injected)
    run_ids.append(load_run.id)

    drop_ids: list[str] = []
    duplicate_ids: list[str] = []
    if scenario == "missing":
        drop_ids = synthetic.pick_ids(rows, synthetic.DROP_COUNT, seed + 1)
        injected["dropped_ids"] = drop_ids
    elif scenario == "duplicate":
        duplicate_ids = synthetic.pick_ids(rows, synthetic.DUPLICATE_COUNT, seed + 2)
        injected["duplicated_ids"] = duplicate_ids

    process_run, process_summary = process_batch(
        session, batch, drop_ids=drop_ids, duplicate_ids=duplicate_ids
    )
    run_ids.append(process_run.id)
    _stamp_injected(session, process_run, injected)

    recon = reconcile(session, batch.id)
    recon_run = PipelineRun(
        batch_id=batch.id, scenario=scenario, stage="reconcile", status="succeeded", summary=recon.to_dict()
    )
    recon_run.finished_at = recon_run.started_at
    session.add(recon_run)
    session.commit()
    run_ids.append(recon_run.id)

    incident = open_incident_from_reconciliation(session, batch, recon_run, recon, process_summary)
    return ScenarioOutcome(scenario, batch.id, run_ids, incident, recon, injected)


def _stamp_injected(session: Session, run: PipelineRun, injected: dict) -> None:
    """Record the injected fault on the run so Day 3 can grade diagnoses against ground truth.

    The incident evidence deliberately does NOT include this; detection must work from data alone.
    """
    run.summary = {**run.summary, "injected_fault": injected}
    session.commit()


def seed_demo(session: Session, engine: Engine, seed: int = 42) -> dict:
    """Reset the database and load the clean batch. Returns a summary for the API."""
    reset_schema(engine)
    outcome = run_scenario(session, "clean", seed=seed)
    rows = synthetic.generate_transactions(seed=seed)
    expected = synthetic.expected_summary(rows)
    return {
        "simulated": True,
        "seed": seed,
        "transactions": expected["count"],
        "expected_sum_cents": expected["sum_cents"],
        "clean": outcome.to_dict(),
    }
