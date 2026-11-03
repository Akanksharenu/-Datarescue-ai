"""Tables for the detect -> investigate -> approve -> recover -> verify flow (ticket DR-004).

Money is stored as integer cents. Timestamps are timezone-aware UTC.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Batch(Base):
    """One incoming batch from the payment source, plus what the source says it should contain."""

    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    scenario: Mapped[str] = mapped_column(String(20))
    business_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD reporting window
    expected_count: Mapped[int] = mapped_column(Integer)
    expected_sum_cents: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TransactionRaw(Base):
    """Immutable copy of what the source sent. source_id is unique within a batch."""

    __tablename__ = "transactions_raw"
    __table_args__ = (UniqueConstraint("batch_id", "source_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(32))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TransactionProcessed(Base):
    """Output of the transformation. The unique constraint is what stops duplicate replays."""

    __tablename__ = "transactions_processed"
    __table_args__ = (UniqueConstraint("batch_id", "source_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(32))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PipelineRun(Base):
    """One execution of one pipeline stage. Written once, never edited after it finishes."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    scenario: Mapped[str] = mapped_column(String(20))
    stage: Mapped[str] = mapped_column(String(20))  # load_raw | process | reconcile
    status: Mapped[str] = mapped_column(String(20))  # running | succeeded | failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class Incident(Base):
    """A detected problem plus an evidence snapshot taken at detection time."""

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id"))
    type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))  # info | warning | critical
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | recovering | resolved
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Investigation(Base):
    """One investigation run against an incident's evidence. Incidents stay immutable."""

    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    method: Mapped[str] = mapped_column(String(10))  # rules | llm
    model: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecoveryRequest(Base):
    """Approval and execution of a recovery are recorded separately (Day 5)."""

    __tablename__ = "recovery_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    proposal: Mapped[dict] = mapped_column(JSON, default=dict)
    approved_by: Mapped[str | None] = mapped_column(String(100))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
