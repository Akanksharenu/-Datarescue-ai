"""Allowlisted fault injection for demos and tests."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import STAGING_MODELS, Batch, Source


class BatchNotFound(Exception):
    pass


@dataclass
class InjectedFault:
    fault_type: str
    source: str
    business_date: date
    rows_removed: int


def inject_missing_batch(session: Session, source_name: str, business_date: date) -> InjectedFault:
    """Remove one batch and its rows, as if the upstream extract never arrived."""
    batch = session.scalars(
        select(Batch)
        .join(Source, Source.id == Batch.source_id)
        .where(Source.name == source_name, Batch.business_date == business_date)
    ).one_or_none()
    if batch is None:
        raise BatchNotFound(f"No {source_name} batch for {business_date}")

    model = STAGING_MODELS[source_name]
    removed = session.execute(delete(model).where(model.batch_id == batch.id)).rowcount
    session.delete(batch)
    session.commit()
    return InjectedFault("missing_batch", source_name, business_date, removed)
