"""Deterministic synthetic transactions and the fault injectors (ticket DR-005).

Same seed => same 1,000 transactions with stable IDs, so every test and demo run is repeatable.
All data here is simulated; it does not represent real customers or revenue.
"""

from datetime import UTC, date, datetime, time, timedelta
from random import Random

BUSINESS_DATE = date(2026, 10, 26)
CLEAN_COUNT = 1000
DROP_COUNT = 280
DUPLICATE_COUNT = 40
RENAMED_FIELD = ("amount_cents", "amount")


def generate_transactions(seed: int = 42, count: int = CLEAN_COUNT, day: date = BUSINESS_DATE) -> list[dict]:
    """Completed, USD transactions that all fall inside one reporting day (UTC)."""
    rng = Random(seed)
    day_start = datetime.combine(day, time(), tzinfo=UTC)
    rows = []
    for n in range(1, count + 1):
        rows.append(
            {
                "source_id": f"TX{n:06d}",
                "amount_cents": rng.randint(500, 50_000),
                "currency": "USD",
                "status": "completed",
                "occurred_at": day_start + timedelta(seconds=rng.randrange(86_400)),
            }
        )
    return rows


def expected_summary(rows: list[dict]) -> dict:
    """What a correct pipeline must reproduce: count, ID set and sum of cents."""
    return {
        "count": len(rows),
        "sum_cents": sum(r["amount_cents"] for r in rows),
        "ids": sorted(r["source_id"] for r in rows),
    }


def pick_ids(rows: list[dict], n: int, seed: int) -> list[str]:
    """Deterministically choose n source IDs from the batch."""
    ids = [r["source_id"] for r in rows]
    return sorted(Random(seed).sample(ids, n))


def rename_field(rows: list[dict], old: str = RENAMED_FIELD[0], new: str = RENAMED_FIELD[1]) -> list[dict]:
    """Simulate an upstream schema change: a required field arrives under a new name."""
    return [{(new if k == old else k): v for k, v in row.items()} for row in rows]
