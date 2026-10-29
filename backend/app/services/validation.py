"""Deterministic reconciliation checks. These decide whether data is correct; no LLM is involved."""

from dataclasses import asdict, dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Batch, TransactionProcessed, TransactionRaw


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # info | warning | critical
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class Reconciliation:
    batch_id: str
    business_date: str
    expected_count: int
    expected_sum_cents: int
    raw_count: int
    processed_count: int
    raw_sum_cents: int
    processed_sum_cents: int
    missing_ids: list[str]
    unexpected_ids: list[str]
    duplicate_ids: list[str]
    findings: list[Finding]

    @property
    def passed(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict:
        data = asdict(self)
        data["missing_count"] = len(self.missing_ids)
        data["unexpected_count"] = len(self.unexpected_ids)
        data["duplicate_count"] = len(self.duplicate_ids)
        data["passed"] = self.passed
        return data


def reconcile(session: Session, batch_id: str) -> Reconciliation:
    """Compare source expectations, raw rows and processed rows for one batch."""
    batch = session.get(Batch, batch_id)
    if batch is None:
        raise ValueError(f"Unknown batch {batch_id}")

    raw_ids = set(
        session.scalars(select(TransactionRaw.source_id).where(TransactionRaw.batch_id == batch_id))
    )
    processed_rows = session.execute(
        select(TransactionProcessed.source_id, func.count())
        .where(TransactionProcessed.batch_id == batch_id)
        .group_by(TransactionProcessed.source_id)
    ).all()
    processed_ids = {sid for sid, _ in processed_rows}
    duplicate_ids = sorted(sid for sid, n in processed_rows if n > 1)
    processed_count = sum(n for _, n in processed_rows)

    raw_sum = int(
        session.scalar(
            select(func.coalesce(func.sum(TransactionRaw.amount_cents), 0)).where(
                TransactionRaw.batch_id == batch_id
            )
        )
    )
    processed_sum = int(
        session.scalar(
            select(func.coalesce(func.sum(TransactionProcessed.amount_cents), 0)).where(
                TransactionProcessed.batch_id == batch_id
            )
        )
    )

    missing_ids = sorted(raw_ids - processed_ids)
    unexpected_ids = sorted(processed_ids - raw_ids)
    findings: list[Finding] = []

    if len(raw_ids) != batch.expected_count:
        findings.append(
            Finding(
                "incomplete_raw_load",
                "critical",
                f"Source promised {batch.expected_count} records but {len(raw_ids)} were loaded into raw.",
                {"expected_count": batch.expected_count, "raw_count": len(raw_ids)},
            )
        )
    if missing_ids:
        findings.append(
            Finding(
                "missing_records",
                "critical",
                f"{len(missing_ids)} raw transactions never reached the processed table.",
                {"missing_count": len(missing_ids), "missing_ids": missing_ids},
            )
        )
    if unexpected_ids:
        findings.append(
            Finding(
                "unexpected_records",
                "critical",
                f"{len(unexpected_ids)} processed transactions have no raw counterpart.",
                {"unexpected_ids": unexpected_ids},
            )
        )
    if duplicate_ids:
        findings.append(
            Finding(
                "duplicate_records",
                "critical",
                f"{len(duplicate_ids)} source IDs are stored more than once in processed.",
                {"duplicate_ids": duplicate_ids},
            )
        )
    if raw_sum != processed_sum:
        findings.append(
            Finding(
                "total_mismatch",
                "critical",
                f"Raw total {raw_sum} cents differs from processed total {processed_sum} cents.",
                {
                    "raw_sum_cents": raw_sum,
                    "processed_sum_cents": processed_sum,
                    "diff_cents": raw_sum - processed_sum,
                },
            )
        )

    window = session.execute(
        select(func.min(TransactionProcessed.occurred_at), func.max(TransactionProcessed.occurred_at)).where(
            TransactionProcessed.batch_id == batch_id
        )
    ).one()
    if window[0] is not None:
        lo, hi = str(window[0])[:10], str(window[1])[:10]
        if lo != batch.business_date or hi != batch.business_date:
            findings.append(
                Finding(
                    "window_mismatch",
                    "warning",
                    f"Processed rows span {lo}..{hi} but the batch reports {batch.business_date}.",
                    {"min_occurred_at": lo, "max_occurred_at": hi},
                )
            )

    bad_status = session.scalar(
        select(func.count()).where(
            TransactionProcessed.batch_id == batch_id, TransactionProcessed.status != "completed"
        )
    )
    if bad_status:
        findings.append(
            Finding(
                "status_inconsistent",
                "warning",
                f"{bad_status} processed rows are not completed; revenue should count completed only.",
                {"non_completed_count": bad_status},
            )
        )

    return Reconciliation(
        batch_id=batch_id,
        business_date=batch.business_date,
        expected_count=batch.expected_count,
        expected_sum_cents=batch.expected_sum_cents,
        raw_count=len(raw_ids),
        processed_count=processed_count,
        raw_sum_cents=raw_sum,
        processed_sum_cents=processed_sum,
        missing_ids=missing_ids,
        unexpected_ids=unexpected_ids,
        duplicate_ids=duplicate_ids,
        findings=findings,
    )
