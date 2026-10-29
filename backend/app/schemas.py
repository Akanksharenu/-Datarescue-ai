"""Pydantic contracts: the incoming-batch schema and API response shapes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Scenario = Literal["clean", "missing", "duplicate", "schema"]


class IncomingTransaction(BaseModel):
    """What the payment source promises to send. Unknown fields are rejected, so a renamed
    field fails loudly instead of being silently filled with a default."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=32)
    amount_cents: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    status: Literal["completed", "pending", "refunded"]
    occurred_at: datetime


class RunSummary(BaseModel):
    id: int
    batch_id: str
    scenario: str
    stage: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    summary: dict


class IncidentSummary(BaseModel):
    id: int
    batch_id: str
    run_id: int | None
    type: str
    severity: str
    status: str
    created_at: datetime


class InvestigationOut(BaseModel):
    id: int
    incident_id: int
    method: Literal["rules", "llm"]
    model: str | None
    likely_cause: str
    explanation: str
    confidence: Literal["high", "medium", "low"]
    uncertainty: str
    supporting_evidence: list[str]
    suggested_next_steps: list[str]
    verified: bool
    unsupported_claims: list[str]
    fallback_reason: str | None
    disclaimer: str
    created_at: datetime


class IncidentDetail(IncidentSummary):
    evidence: dict
    lineage: dict | None = None
    investigations: list[InvestigationOut] = []


class LineageOut(BaseModel):
    path: list[str]
    edges: list[dict]


class ApproveRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=100, description="Demo-only approver name")


class RejectRequest(BaseModel):
    rejected_by: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)


class RecoveryOut(BaseModel):
    id: int
    incident_id: int
    action: str
    status: str
    proposal: dict
    approved_by: str | None
    approved_at: datetime | None
    executed_at: datetime | None
    result: dict | None
    created_at: datetime


class Finding(BaseModel):
    code: str
    severity: str
    message: str
    details: dict


class ReconciliationOut(BaseModel):
    batch_id: str
    business_date: str
    expected_count: int
    expected_sum_cents: int
    raw_count: int
    processed_count: int
    raw_sum_cents: int
    processed_sum_cents: int
    missing_count: int
    unexpected_count: int
    duplicate_count: int
    passed: bool
    findings: list[Finding]


class ScenarioResult(BaseModel):
    simulated: bool = True
    scenario: str
    batch_id: str
    run_ids: list[int]
    incident_id: int | None
    reconciliation: ReconciliationOut | None


class SeedResult(BaseModel):
    simulated: bool = True
    seed: int
    transactions: int
    expected_sum_cents: int
    clean: ScenarioResult
