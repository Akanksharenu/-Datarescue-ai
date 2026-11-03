"""Critical endpoints respond with the right shapes and status codes."""


def test_seed_then_run_missing_flow(client):
    seeded = client.post("/demo/seed")
    assert seeded.status_code == 200
    body = seeded.json()
    assert body["simulated"] is True
    assert body["transactions"] == 1000
    assert body["clean"]["incident_id"] is None
    assert body["clean"]["reconciliation"]["passed"] is True

    run = client.post("/demo/run", params={"scenario": "missing"})
    assert run.status_code == 200
    result = run.json()
    assert result["batch_id"] == "missing-001"
    assert result["reconciliation"]["missing_count"] == 280
    incident_id = result["incident_id"]
    assert incident_id is not None

    incidents = client.get("/incidents").json()
    assert [i["id"] for i in incidents] == [incident_id]
    assert incidents[0]["type"] == "missing_records"
    assert "evidence" not in incidents[0]

    detail = client.get(f"/incidents/{incident_id}").json()
    assert detail["evidence"]["reconciliation"]["missing_count"] == 280
    assert len(detail["evidence"]["reconciliation"]["missing_ids"]) == 280

    runs = client.get("/pipeline-runs").json()
    assert len(runs) == 6  # 3 stages for clean + 3 for missing
    assert {r["stage"] for r in runs} == {"load_raw", "process", "reconcile"}

    recon = client.get("/batches/missing-001/reconciliation").json()
    assert recon["passed"] is False
    assert recon["processed_count"] == 720


def test_schema_scenario_via_api(client):
    client.post("/demo/seed")
    result = client.post("/demo/run", params={"scenario": "schema"}).json()
    assert result["reconciliation"] is None
    detail = client.get(f"/incidents/{result['incident_id']}").json()
    assert detail["type"] == "schema_mismatch"
    assert detail["evidence"]["missing_fields"] == ["amount_cents"]


def test_unknown_scenario_is_rejected(client):
    assert client.post("/demo/run", params={"scenario": "explode"}).status_code == 422


def test_missing_incident_returns_404(client):
    assert client.get("/incidents/999").status_code == 404
    assert client.get("/batches/nope/reconciliation").status_code == 404
