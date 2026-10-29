"""The two pipeline stages: load_raw (source -> raw) and process_batch (raw -> processed).

Every execution is recorded in pipeline_runs, including failures. Faults are passed in
explicitly by the demo runner so the stages themselves stay honest and testable.
"""

from dataclasses import asdict, dataclass, field

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Batch, PipelineRun, TransactionProcessed, TransactionRaw, utcnow
from app.schemas import IncomingTransaction


class SchemaMismatchError(Exception):
    """Incoming rows do not match the IncomingTransaction contract."""

    def __init__(self, errors: list[dict], rows_rejected: int):
        self.errors = errors
        self.rows_rejected = rows_rejected
        missing = sorted({e["field"] for e in errors if e["kind"] == "missing"})
        extra = sorted({e["field"] for e in errors if e["kind"] == "extra_forbidden"})
        super().__init__(
            f"Incoming batch failed schema validation: {rows_rejected} rows rejected; "
            f"missing fields {missing}; unexpected fields {extra}"
        )


@dataclass
class LoadSummary:
    batch_id: str
    rows_received: int
    rows_loaded: int
    rows_rejected: int = 0
    validation_errors: list[dict] = field(default_factory=list)


@dataclass
class ProcessSummary:
    batch_id: str
    raw_count: int
    rows_attempted: int
    rows_inserted: int
    duplicates_rejected: list[str] = field(default_factory=list)
    rows_dropped: list[str] = field(default_factory=list)


def validate_incoming(rows: list[dict]) -> tuple[list[IncomingTransaction], list[dict]]:
    """Validate each row against the contract. Returns (valid rows, error records)."""
    valid: list[IncomingTransaction] = []
    errors: list[dict] = []
    for index, row in enumerate(rows):
        try:
            valid.append(IncomingTransaction.model_validate(row))
        except ValidationError as exc:
            for err in exc.errors():
                errors.append(
                    {
                        "row_index": index,
                        "field": ".".join(str(p) for p in err["loc"]) or "<row>",
                        "kind": err["type"],
                        "message": err["msg"],
                    }
                )
    return valid, errors


def _start_run(session: Session, batch: Batch, stage: str) -> PipelineRun:
    run = PipelineRun(batch_id=batch.id, scenario=batch.scenario, stage=stage, status="running")
    session.add(run)
    session.flush()
    return run


def _finish_run(
    session: Session, run: PipelineRun, status: str, summary: dict, error: str | None = None
) -> None:
    run.status = status
    run.summary = summary
    run.error = error
    run.finished_at = utcnow()
    session.commit()


def load_raw(session: Session, batch: Batch, rows: list[dict]) -> tuple[PipelineRun, LoadSummary]:
    """Validate the incoming batch and store it unchanged in transactions_raw.

    A schema failure loads nothing, records a failed run and raises SchemaMismatchError.
    """
    run = _start_run(session, batch, "load_raw")
    valid, errors = validate_incoming(rows)
    if errors:
        rejected = len({e["row_index"] for e in errors})
        summary = LoadSummary(batch.id, len(rows), 0, rejected, errors[:20])
        exc = SchemaMismatchError(errors, rejected)
        _finish_run(session, run, "failed", asdict(summary), str(exc))
        raise exc

    session.add_all(TransactionRaw(batch_id=batch.id, **tx.model_dump()) for tx in valid)
    summary = LoadSummary(batch.id, len(rows), len(valid))
    _finish_run(session, run, "succeeded", asdict(summary))
    return run, summary


def _insert_ignore(session: Session, rows: list[dict]) -> int:
    """INSERT ... ON CONFLICT DO NOTHING so the unique constraint, not Python, blocks duplicates."""
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert

    stmt = (
        insert(TransactionProcessed)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["batch_id", "source_id"])
    )
    return session.execute(stmt).rowcount


def process_batch(
    session: Session,
    batch: Batch,
    drop_ids: list[str] | None = None,
    duplicate_ids: list[str] | None = None,
    stage: str = "process",
) -> tuple[PipelineRun, ProcessSummary]:
    """Copy raw rows into transactions_processed.

    drop_ids / duplicate_ids simulate a buggy transformation. Duplicate inserts are attempted
    for real and rejected by the database unique constraint; the rejection count is recorded.
    stage="replay" is used by recovery; the logic is identical, which is the point: a replay
    is the same idempotent upsert, so running it twice cannot add rows.
    """
    drop = set(drop_ids or [])
    dup = set(duplicate_ids or [])
    run = _start_run(session, batch, stage)
    try:
        raw = list(session.scalars(select(TransactionRaw).where(TransactionRaw.batch_id == batch.id)))
        candidates: list[dict] = []
        for tx in raw:
            if tx.source_id in drop:
                continue
            row = {
                "batch_id": batch.id,
                "source_id": tx.source_id,
                "amount_cents": tx.amount_cents,
                "currency": tx.currency,
                "status": tx.status,
                "occurred_at": tx.occurred_at,
            }
            candidates.append(row)
            if tx.source_id in dup:
                candidates.append(dict(row))

        inserted = 0
        if candidates:
            inserted = sum(
                _insert_ignore(session, candidates[i : i + 500]) for i in range(0, len(candidates), 500)
            )
        attempted_ids = [c["source_id"] for c in candidates]
        rejected = sorted({sid for sid in attempted_ids if attempted_ids.count(sid) > 1}) if dup else []

        summary = ProcessSummary(
            batch_id=batch.id,
            raw_count=len(raw),
            rows_attempted=len(candidates),
            rows_inserted=inserted,
            duplicates_rejected=rejected,
            rows_dropped=sorted(drop & {tx.source_id for tx in raw}),
        )
        _finish_run(session, run, "succeeded", asdict(summary))
        return run, summary
    except Exception as exc:
        session.rollback()
        _finish_run(session, run, "failed", {}, f"{type(exc).__name__}: {exc}")
        raise
