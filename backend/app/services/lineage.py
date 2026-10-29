"""Basic lineage: which datasets sit downstream of a failure (ticket DR-007).

payment_source -> raw_transactions -> processed_transactions -> revenue_report
"""

NODES = ["payment_source", "raw_transactions", "processed_transactions", "revenue_report"]

# (upstream, downstream, transform that produces downstream)
EDGES = [
    ("payment_source", "raw_transactions", "load_raw"),
    ("raw_transactions", "processed_transactions", "process_batch"),
    ("processed_transactions", "revenue_report", "build_revenue_report"),
]

# Which transform an incident type implicates. Everything downstream of it is affected.
FAILED_STEP_BY_TYPE = {
    "schema_mismatch": "load_raw",
    "incomplete_raw_load": "load_raw",
    "missing_records": "process_batch",
    "unexpected_records": "process_batch",
    "total_mismatch": "process_batch",
    "window_mismatch": "process_batch",
    "status_inconsistent": "process_batch",
    "duplicate_records": "process_batch",
}


def downstream_of(node: str) -> list[str]:
    """Every dataset reachable from node, in pipeline order."""
    result: list[str] = []
    frontier = [node]
    while frontier:
        current = frontier.pop(0)
        for upstream, downstream, _ in EDGES:
            if upstream == current and downstream not in result:
                result.append(downstream)
                frontier.append(downstream)
    return result


def impact(incident_type: str, duplicates_blocked: bool = False) -> dict:
    """Describe where the pipeline broke and which datasets can no longer be trusted.

    duplicates_blocked=True means the unique constraint rejected the duplicates, so no
    dataset is actually corrupted; downstream datasets are marked at risk instead.
    """
    step = FAILED_STEP_BY_TYPE.get(incident_type, "process_batch")
    upstream_node = next(u for u, _, t in EDGES if t == step)
    produced = next(d for _, d, t in EDGES if t == step)
    downstream = [produced, *downstream_of(produced)]
    intact = NODES[: NODES.index(upstream_node) + 1]

    if duplicates_blocked:
        return {
            "path": NODES,
            "edges": [{"from": u, "to": d, "transform": t} for u, d, t in EDGES],
            "failed_step": step,
            "affected_datasets": [],
            "at_risk_datasets": downstream,
            "intact_datasets": NODES,
            "note": "Duplicates were rejected by the unique constraint; no dataset was corrupted.",
        }
    return {
        "path": NODES,
        "edges": [{"from": u, "to": d, "transform": t} for u, d, t in EDGES],
        "failed_step": step,
        "affected_datasets": downstream,
        "at_risk_datasets": [],
        "intact_datasets": intact,
        "note": f"{step} did not reproduce its input; everything it feeds is suspect.",
    }
