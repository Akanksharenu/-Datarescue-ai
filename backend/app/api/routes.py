from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import Batch, Incident, Investigation, PipelineRun, RecoveryRequest
from app.schemas import (
    ApproveRequest,
    IncidentDetail,
    IncidentSummary,
    InvestigationOut,
    LineageOut,
    ReconciliationOut,
    RecoveryOut,
    RejectRequest,
    RunSummary,
    Scenario,
    ScenarioResult,
    SeedResult,
)
from app.services.demo import run_scenario, seed_demo
from app.services.investigation import investigate
from app.services.lineage import EDGES, NODES
from app.services.recovery import (
    RecoveryError,
    approve_recovery,
    execute_recovery,
    propose_recovery,
    reject_recovery,
)
from app.services.validation import reconcile

router = APIRouter()


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.post("/demo/seed", response_model=SeedResult)
def demo_seed(session: Session = Depends(get_session)):
    """Reset the database and load the reproducible clean batch (simulated data)."""
    return seed_demo(session, session.get_bind(), seed=settings.seed)


@router.post("/demo/run", response_model=ScenarioResult)
def demo_run(scenario: Scenario = Query(...), session: Session = Depends(get_session)):
    """Execute one controlled scenario: clean, missing, duplicate or schema."""
    try:
        outcome = run_scenario(session, scenario, seed=settings.seed)
    except Exception as exc:  # the run itself is recorded as failed; surface a readable error
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Scenario failed: {exc}") from exc
    return outcome.to_dict()


@router.get("/pipeline-runs", response_model=list[RunSummary])
def list_runs(session: Session = Depends(get_session)):
    return list(session.scalars(select(PipelineRun).order_by(PipelineRun.id.desc())))


@router.get("/incidents", response_model=list[IncidentSummary])
def list_incidents(session: Session = Depends(get_session)):
    return list(session.scalars(select(Incident).order_by(Incident.id.desc())))


def _investigation_out(inv: Investigation) -> dict:
    return {"id": inv.id, "incident_id": inv.incident_id, "created_at": inv.created_at, **inv.result}


def _get_incident_or_404(session: Session, incident_id: int) -> Incident:
    incident = session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return incident


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
def get_incident(incident_id: int, session: Session = Depends(get_session)):
    incident = _get_incident_or_404(session, incident_id)
    investigations = session.scalars(
        select(Investigation)
        .where(Investigation.incident_id == incident_id)
        .order_by(Investigation.id.desc())
    )
    return {
        "id": incident.id,
        "batch_id": incident.batch_id,
        "run_id": incident.run_id,
        "type": incident.type,
        "severity": incident.severity,
        "status": incident.status,
        "created_at": incident.created_at,
        "evidence": incident.evidence,
        "lineage": incident.evidence.get("lineage"),
        "investigations": [_investigation_out(i) for i in investigations],
    }


@router.post("/incidents/{incident_id}/investigate", response_model=InvestigationOut)
def investigate_incident(
    incident_id: int,
    method: Literal["auto", "rules"] = Query("auto", description="auto uses Claude when a key is set"),
    session: Session = Depends(get_session),
):
    """Read-only investigation of the stored evidence. Never touches pipeline or recovery tables."""
    incident = _get_incident_or_404(session, incident_id)
    result = investigate(incident.evidence, settings.anthropic_api_key, settings.llm_model, method=method)
    row = Investigation(
        incident_id=incident.id, method=result.method, model=result.model, result=result.model_dump()
    )
    session.add(row)
    session.commit()
    return _investigation_out(row)


# --- Recovery (Day 5): propose -> approve -> execute -> proof --------------------


def _get_recovery_or_404(session: Session, request_id: int) -> RecoveryRequest:
    request = session.get(RecoveryRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail=f"Recovery request {request_id} not found")
    return request


def _recovery_call(session: Session, fn, *args) -> RecoveryRequest:
    try:
        return fn(session, *args)
    except RecoveryError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/incidents/{incident_id}/recovery", response_model=RecoveryOut, status_code=201)
def propose(incident_id: int, session: Session = Depends(get_session)):
    """Create a recovery proposal: planned action, expected effect, and validation preconditions."""
    incident = _get_incident_or_404(session, incident_id)
    return _recovery_call(session, propose_recovery, incident)


@router.get("/recovery", response_model=list[RecoveryOut])
def list_recovery(session: Session = Depends(get_session)):
    return list(session.scalars(select(RecoveryRequest).order_by(RecoveryRequest.id.desc())))


@router.get("/recovery/{request_id}", response_model=RecoveryOut)
def get_recovery(request_id: int, session: Session = Depends(get_session)):
    return _get_recovery_or_404(session, request_id)


@router.post("/recovery/{request_id}/approve", response_model=RecoveryOut)
def approve(request_id: int, body: ApproveRequest, session: Session = Depends(get_session)):
    """Record an explicit approval. Demo-only identity; not production authorization."""
    request = _get_recovery_or_404(session, request_id)
    return _recovery_call(session, approve_recovery, request, body.approved_by)


@router.post("/recovery/{request_id}/reject", response_model=RecoveryOut)
def reject(request_id: int, body: RejectRequest, session: Session = Depends(get_session)):
    request = _get_recovery_or_404(session, request_id)
    return _recovery_call(session, reject_recovery, request, body.rejected_by, body.reason)


@router.post("/recovery/{request_id}/execute", response_model=RecoveryOut)
def execute(request_id: int, session: Session = Depends(get_session)):
    """Replay the batch (approved requests only), revalidate, and return the proof record."""
    request = _get_recovery_or_404(session, request_id)
    return _recovery_call(session, execute_recovery, request)


@router.get("/lineage", response_model=LineageOut)
def lineage():
    """The static dataset graph: payment_source -> raw -> processed -> revenue_report."""
    return {"path": NODES, "edges": [{"from": u, "to": d, "transform": t} for u, d, t in EDGES]}


@router.get("/batches/{batch_id}/reconciliation", response_model=ReconciliationOut)
def batch_reconciliation(batch_id: str, session: Session = Depends(get_session)):
    """Re-run the deterministic checks against the current database state."""
    if session.get(Batch, batch_id) is None:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")
    return reconcile(session, batch_id).to_dict()
