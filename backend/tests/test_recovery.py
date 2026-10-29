"""Day 5 test matrix: approved replay reconciles, repeated replay adds nothing, unapproved
replay is rejected and recorded, unsupported actions and invalid transitions are refused."""

import pytest
from sqlalchemy import func, select

from app.models import Incident, PipelineRun, TransactionProcessed
from app.services.demo import run_scenario
from app.services.recovery import (
    RecoveryError,
    approve_recovery,
    execute_recovery,
    propose_recovery,
    reject_recovery,
)
from app.services.validation import reconcile


def _processed_count(session, batch_id):
    return session.scalar(select(func.count()).where(TransactionProcessed.batch_id == batch_id))


@pytest.fixture
def missing_incident(session):
    outcome = run_scenario(session, "missing")
    return outcome.incident


def test_proposal_shows_batch_action_expected_effect_and_preconditions(session, missing_incident):
    request = propose_recovery(session, missing_incident)

    assert request.status == "proposed"
    assert request.action == "replay_batch"
    p = request.proposal
    assert p["batch_id"] == missing_incident.batch_id
    assert p["expected_inserts"] == 280
    assert p["expected_updates"] == 0
    assert p["expected_processed_count_after"] == 1000
    assert p["before"]["processed_count"] == 720
    assert p["preconditions_met"] is True
    assert {c["name"] for c in p["preconditions"]} >= {"raw_is_complete", "processed_has_no_duplicates"}


def test_approved_replay_returns_batch_to_reconciled_state(session, missing_incident):
    request = propose_recovery(session, missing_incident)
    approve_recovery(session, request, "demo-approver")
    assert request.status == "approved" and request.approved_at is not None
    assert session.get(Incident, missing_incident.id).status == "recovering"

    execute_recovery(session, request)

    assert request.status == "executed"
    proof = request.result
    assert proof["status"] == "verified"
    assert proof["before"]["processed_count"] == 720
    assert proof["after"]["processed_count"] == 1000
    assert proof["rows_inserted_this_run"] == 280
    assert proof["approval"]["approved_by"] == "demo-approver"
    assert all(c["passed"] for c in proof["checks"])
    assert {c["name"] for c in proof["checks"]} >= {
        "source_id_set_matches",
        "count_matches",
        "amount_totals_match",
        "no_duplicates",
    }

    after = reconcile(session, missing_incident.batch_id)
    assert after.passed
    assert after.raw_sum_cents == after.processed_sum_cents
    assert session.get(Incident, missing_incident.id).status == "resolved"

    replay_run = session.get(PipelineRun, proof["executions"][0]["run_id"])
    assert replay_run.stage == "replay" and replay_run.status == "succeeded"


def test_repeated_approved_replay_adds_no_records_or_revenue(session, missing_incident):
    request = propose_recovery(session, missing_incident)
    approve_recovery(session, request, "demo-approver")
    execute_recovery(session, request)
    sum_after_first = reconcile(session, missing_incident.batch_id).processed_sum_cents

    execute_recovery(session, request)

    assert request.status == "executed"
    assert len(request.result["executions"]) == 2
    assert request.result["executions"][1]["rows_inserted"] == 0
    assert request.result["executions"][1]["rows_attempted"] == 1000
    assert _processed_count(session, missing_incident.batch_id) == 1000
    assert reconcile(session, missing_incident.batch_id).processed_sum_cents == sum_after_first


def test_unapproved_replay_is_rejected_and_recorded(session, missing_incident):
    request = propose_recovery(session, missing_incident)

    with pytest.raises(RecoveryError) as exc:
        execute_recovery(session, request)

    assert exc.value.status_code == 409
    assert request.status == "proposed"
    assert _processed_count(session, missing_incident.batch_id) == 720  # nothing changed
    refused = request.result["refused_attempts"]
    assert len(refused) == 1 and "not approved" in refused[0]["reason"]
    run = session.get(PipelineRun, refused[0]["run_id"])
    assert run.stage == "replay" and run.status == "failed" and run.error.startswith("refused")


def test_blocked_duplicates_need_no_recovery(session):
    incident = run_scenario(session, "duplicate").incident
    with pytest.raises(RecoveryError) as exc:
        propose_recovery(session, incident)
    assert exc.value.status_code == 422
    assert "intact" in str(exc.value)


def test_schema_incident_has_no_replay_action(session):
    incident = run_scenario(session, "schema").incident
    with pytest.raises(RecoveryError) as exc:
        propose_recovery(session, incident)
    assert exc.value.status_code == 422
    assert "corrected extract" in str(exc.value)


def test_invalid_transitions_are_refused(session, missing_incident):
    request = propose_recovery(session, missing_incident)

    with pytest.raises(RecoveryError):
        propose_recovery(session, missing_incident)  # one open request per incident

    approve_recovery(session, request, "demo-approver")
    with pytest.raises(RecoveryError):
        approve_recovery(session, request, "someone-else")  # already approved
    with pytest.raises(RecoveryError):
        reject_recovery(session, request, "someone", "too late")  # cannot reject an approved request

    execute_recovery(session, request)
    with pytest.raises(RecoveryError):
        propose_recovery(session, missing_incident)  # resolved incidents cannot be re-proposed


def test_rejected_request_cannot_execute(session, missing_incident):
    request = propose_recovery(session, missing_incident)
    reject_recovery(session, request, "reviewer", "wait for source confirmation")
    assert request.status == "rejected"
    with pytest.raises(RecoveryError):
        execute_recovery(session, request)
    assert _processed_count(session, missing_incident.batch_id) == 720


def test_full_recovery_flow_over_the_api(client):
    client.post("/demo/seed")
    run = client.post("/demo/run", params={"scenario": "missing"}).json()
    incident_id = run["incident_id"]

    proposal = client.post(f"/incidents/{incident_id}/recovery")
    assert proposal.status_code == 201
    request_id = proposal.json()["id"]
    assert proposal.json()["proposal"]["expected_inserts"] == 280

    refused = client.post(f"/recovery/{request_id}/execute")
    assert refused.status_code == 409
    # Read it back over the API (fresh session): the refusal must be persisted with its run id.
    recorded = client.get(f"/recovery/{request_id}").json()["result"]["refused_attempts"]
    assert len(recorded) == 1 and isinstance(recorded[0]["run_id"], int)

    bad_approval = client.post(f"/recovery/{request_id}/approve", json={"approved_by": ""})
    assert bad_approval.status_code == 422

    approved = client.post(f"/recovery/{request_id}/approve", json={"approved_by": "demo-approver"})
    assert approved.status_code == 200 and approved.json()["status"] == "approved"

    executed = client.post(f"/recovery/{request_id}/execute")
    assert executed.status_code == 200
    proof = executed.json()["result"]
    assert proof["status"] == "verified"
    assert proof["after"]["processed_count"] == 1000
    assert proof["refused_attempts"] == recorded  # the earlier refusal survives execution

    recon = client.get(f"/batches/{run['batch_id']}/reconciliation").json()
    assert recon["passed"] is True
    assert client.get(f"/incidents/{incident_id}").json()["status"] == "resolved"
    assert client.get("/recovery").json()[0]["id"] == request_id
    assert client.get("/recovery/999").status_code == 404

    runs = client.get("/pipeline-runs").json()
    assert [r["stage"] for r in runs if r["batch_id"] == run["batch_id"]][:2] == ["replay", "replay"]
    assert {r["status"] for r in runs if r["stage"] == "replay"} == {"failed", "succeeded"}


def test_duplicate_incident_recovery_rejected_over_api(client):
    client.post("/demo/seed")
    run = client.post("/demo/run", params={"scenario": "duplicate"}).json()
    response = client.post(f"/incidents/{run['incident_id']}/recovery")
    assert response.status_code == 422
    assert session_count_is_zero(client)


def session_count_is_zero(client) -> bool:
    return client.get("/recovery").json() == []
