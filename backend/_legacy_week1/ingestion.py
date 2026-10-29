"""Idempotent batch loads: loading the same (source, business_date) twice leaves the data unchanged."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import STAGING_MODELS, Base, Batch, JobRun, Source, utcnow


def _upsert(session: Session, model: type[Base], rows: list[dict]) -> None:
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert

    key = model.__table__.primary_key.columns.keys()[0]
    stmt = insert(model).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[key],
        set_={c.name: stmt.excluded[c.name] for c in model.__table__.columns if c.name != key},
    )
    session.execute(stmt)


def load_batch(
    session: Session, source_name: str, business_date: date, rows: list[dict], origin: str = "seed"
) -> Batch:
    """Load one source's rows for one business date and record an immutable job run."""
    source = session.scalars(select(Source).where(Source.name == source_name)).one()
    run = JobRun(job_name=f"ingest_{source_name}", status="running", started_at=utcnow())
    session.add(run)

    batch = session.scalars(
        select(Batch).where(Batch.source_id == source.id, Batch.business_date == business_date)
    ).one_or_none()
    if batch is None:
        batch = Batch(source_id=source.id, business_date=business_date, origin=origin)
        session.add(batch)
    batch.origin = origin
    batch.row_count = len(rows)
    batch.loaded_at = utcnow()
    session.flush()

    if rows:
        _upsert(session, STAGING_MODELS[source_name], [{**row, "batch_id": batch.id} for row in rows])

    run.batch_id = batch.id
    run.status = "succeeded"
    run.rows_written = len(rows)
    run.finished_at = utcnow()
    session.commit()
    return batch
