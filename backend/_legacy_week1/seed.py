"""Load reference data and 30 days of synthetic batches. Run after `alembic upgrade head`.

    python -m app.seed
"""

from sqlalchemy.orm import Session

from app.config import settings
from app.services.ingestion import load_batch
from app.services.reference import seed_reference_data
from app.services.synthetic import generate


def seed_all(session: Session, seed: int, **generate_kwargs) -> int:
    seed_reference_data(session)
    data = generate(seed=seed, **generate_kwargs)
    for source, batches in data.by_source().items():
        for business_date, rows in batches.items():
            load_batch(session, source, business_date, rows)
    return data.total_rows()


def main() -> None:
    from app.db import SessionLocal

    with SessionLocal() as session:
        total = seed_all(session, settings.seed)
    print(f"Seeded {total} records with seed={settings.seed}")


if __name__ == "__main__":
    main()
