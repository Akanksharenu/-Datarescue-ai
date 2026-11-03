"""Static reference data: the three sources and the dataset lineage DAG."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Dataset, LineageEdge, Source

SOURCES = {"orders": "transactional", "payments": "transactional", "crm": "crm"}

DATASETS = {
    "raw_orders": "raw",
    "raw_payments": "raw",
    "raw_crm": "raw",
    "fct_orders_payments": "fact",
    "rpt_daily_revenue": "report",
}

# (upstream, downstream, transform)
EDGES = [
    ("raw_orders", "fct_orders_payments", "build_fct_orders_payments"),
    ("raw_payments", "fct_orders_payments", "build_fct_orders_payments"),
    ("raw_crm", "fct_orders_payments", "build_fct_orders_payments"),
    ("fct_orders_payments", "rpt_daily_revenue", "build_rpt_daily_revenue"),
]


def seed_reference_data(session: Session) -> None:
    """Insert sources, datasets and lineage edges. Safe to run repeatedly."""
    existing_sources = set(session.scalars(select(Source.name)))
    for name, kind in SOURCES.items():
        if name not in existing_sources:
            session.add(Source(name=name, kind=kind))

    datasets = {d.name: d for d in session.scalars(select(Dataset))}
    for name, layer in DATASETS.items():
        if name not in datasets:
            datasets[name] = Dataset(name=name, layer=layer)
            session.add(datasets[name])
    session.flush()

    existing_edges = set(session.execute(select(LineageEdge.upstream_id, LineageEdge.downstream_id)))
    for upstream, downstream, transform in EDGES:
        key = (datasets[upstream].id, datasets[downstream].id)
        if key not in existing_edges:
            session.add(LineageEdge(upstream_id=key[0], downstream_id=key[1], transform=transform))
    session.commit()
