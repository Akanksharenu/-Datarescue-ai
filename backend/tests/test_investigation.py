"""Day 3 acceptance: investigations are grounded in evidence, rules work without a key,
the AI path never touches the database, and uncertain cases are reported as uncertain."""

from app.services.demo import run_scenario
from app.services.investigation import (
    DISCLAIMER,
    Diagnosis,
    diagnose_with_rules,
    investigate,
    resolve_path,
    verify_claims,
)


def _evidence(session, scenario):
    outcome = run_scenario(session, scenario)
    return outcome.incident.evidence, outcome.injected


def test_rules_diagnose_missing_scenario(session):
    evidence, injected = _evidence(session, "missing")
    result = diagnose_with_rules(evidence)
    assert result.method == "rules"
    assert result.likely_cause == "transformation_dropped_records"
    assert result.confidence == "high"
    assert result.verified and result.unsupported_claims == []
    assert "reconciliation.missing_ids" in result.supporting_evidence
    assert str(len(injected["dropped_ids"])) in result.explanation


def test_rules_diagnose_duplicate_scenario(session):
    evidence, _ = _evidence(session, "duplicate")
    result = diagnose_with_rules(evidence)
    assert result.likely_cause == "duplicate_source_rows_blocked"
    assert result.verified
    assert any("No recovery needed" in step for step in result.suggested_next_steps)


def test_rules_diagnose_schema_scenario(session):
    evidence, _ = _evidence(session, "schema")
    result = diagnose_with_rules(evidence)
    assert result.likely_cause == "upstream_schema_change"
    assert "amount_cents -> amount" in result.explanation
    assert result.verified


def test_rules_report_uncertainty_on_empty_evidence():
    result = diagnose_with_rules({})
    assert result.likely_cause == "insufficient_evidence"
    assert result.confidence == "low"


def test_rules_handle_ambiguous_total_mismatch_without_missing_rows():
    evidence = {
        "reconciliation": {
            "raw_count": 10,
            "processed_count": 10,
            "raw_sum_cents": 1000,
            "processed_sum_cents": 990,
            "findings": [{"code": "total_mismatch", "severity": "critical"}],
        }
    }
    result = diagnose_with_rules(evidence)
    assert result.likely_cause == "amount_altered_in_transform"
    assert result.confidence == "medium"


def test_verify_claims_flags_paths_that_do_not_exist():
    evidence = {"reconciliation": {"missing_count": 3, "findings": [{"code": "x"}]}}
    assert resolve_path(evidence, "reconciliation.findings.0.code") == (True, "x")
    diagnosis = Diagnosis(
        likely_cause="no_fault",
        explanation="",
        confidence="low",
        uncertainty="",
        supporting_evidence=["reconciliation.missing_count", "reconciliation.made_up", "nope"],
        suggested_next_steps=[],
    )
    assert verify_claims(diagnosis, evidence) == ["reconciliation.made_up", "nope"]


def test_investigate_without_key_uses_rules_and_says_so():
    result = investigate({}, api_key="", model="claude-opus-5-5", method="auto")
    assert result.method == "rules"
    assert result.fallback_reason == "no API key configured"
    assert result.disclaimer == DISCLAIMER


def test_investigate_forced_rules_ignores_key():
    result = investigate({}, api_key="sk-fake", model="claude-opus-5-5", method="rules")
    assert result.method == "rules"
    assert result.fallback_reason is None


def test_investigate_route_persists_and_never_mutates_pipeline_tables(client):
    client.post("/demo/seed")
    run = client.post("/demo/run", params={"scenario": "missing"}).json()
    before_runs = client.get("/pipeline-runs").json()
    before_recon = client.get(f"/batches/{run['batch_id']}/reconciliation").json()

    response = client.post(f"/incidents/{run['incident_id']}/investigate", params={"method": "rules"})
    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "rules"
    assert body["likely_cause"] == "transformation_dropped_records"
    assert body["verified"] is True

    detail = client.get(f"/incidents/{run['incident_id']}").json()
    assert detail["lineage"]["affected_datasets"] == ["processed_transactions", "revenue_report"]
    assert len(detail["investigations"]) == 1
    assert detail["investigations"][0]["id"] == body["id"]

    assert client.get("/pipeline-runs").json() == before_runs
    assert client.get(f"/batches/{run['batch_id']}/reconciliation").json() == before_recon


def test_investigate_unknown_incident_is_404(client):
    client.post("/demo/seed")
    assert client.post("/incidents/42/investigate").status_code == 404


def test_lineage_route(client):
    body = client.get("/lineage").json()
    assert body["path"][0] == "payment_source" and body["path"][-1] == "revenue_report"
    assert len(body["edges"]) == 3
