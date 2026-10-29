from app.services.lineage import NODES, downstream_of, impact


def test_path_order():
    assert NODES == ["payment_source", "raw_transactions", "processed_transactions", "revenue_report"]
    assert downstream_of("raw_transactions") == ["processed_transactions", "revenue_report"]
    assert downstream_of("revenue_report") == []


def test_schema_failure_affects_everything_after_load():
    result = impact("schema_mismatch")
    assert result["failed_step"] == "load_raw"
    assert result["affected_datasets"] == ["raw_transactions", "processed_transactions", "revenue_report"]
    assert result["intact_datasets"] == ["payment_source"]


def test_missing_records_affects_processed_and_report():
    result = impact("missing_records")
    assert result["failed_step"] == "process_batch"
    assert result["affected_datasets"] == ["processed_transactions", "revenue_report"]
    assert result["intact_datasets"] == ["payment_source", "raw_transactions"]


def test_blocked_duplicates_corrupt_nothing():
    result = impact("duplicate_records", duplicates_blocked=True)
    assert result["affected_datasets"] == []
    assert result["at_risk_datasets"] == ["processed_transactions", "revenue_report"]
    assert result["intact_datasets"] == NODES
