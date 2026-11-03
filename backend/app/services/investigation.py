"""Incident investigation (ticket DR-008).

Two read-only diagnosers produce the same structured result:

* diagnose_with_rules  - deterministic templates; always available; method="rules".
* diagnose_with_claude - optional LLM; only runs when an API key is configured; method="llm".

Both consume ONLY the incident evidence dict. Neither touches the database or the recovery
functions. Every LLM claim is checked against the evidence and marked unverified if it
points at data that does not exist.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

Cause = Literal[
    "upstream_schema_change",
    "transformation_dropped_records",
    "duplicate_source_rows_blocked",
    "duplicate_rows_stored",
    "amount_altered_in_transform",
    "processed_contains_foreign_rows",
    "source_extract_incomplete",
    "wrong_reporting_window",
    "status_filter_mismatch",
    "no_fault",
    "insufficient_evidence",
]
CAUSES: tuple[str, ...] = Cause.__args__  # type: ignore[attr-defined]

Confidence = Literal["high", "medium", "low"]

DISCLAIMER = (
    "Investigation output is a suggestion grounded in recorded evidence. It does not decide "
    "financial correctness and must be confirmed by the deterministic reconciliation checks "
    "and a human before any recovery."
)


class Diagnosis(BaseModel):
    """What a diagnoser returns. This is also the structured output schema given to the LLM."""

    likely_cause: Cause
    explanation: str = Field(description="Two or three sentences grounded in the evidence.")
    confidence: Confidence
    uncertainty: str = Field(description="What the evidence cannot establish.")
    supporting_evidence: list[str] = Field(
        description="Dotted paths into the evidence JSON that support the cause, e.g. "
        "'reconciliation.missing_count'. Only paths that exist."
    )
    suggested_next_steps: list[str] = Field(description="Actions for a human engineer. Never writes.")


class InvestigationResult(Diagnosis):
    method: Literal["rules", "llm"]
    model: str | None = None
    verified: bool = False
    unsupported_claims: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None
    disclaimer: str = DISCLAIMER


# --- Evidence helpers ---------------------------------------------------------


def resolve_path(evidence: dict, path: str) -> tuple[bool, Any]:
    """Follow a dotted path like reconciliation.findings.0.code through dicts and lists."""
    node: Any = evidence
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return False, None
    return True, node


def verify_claims(diagnosis: Diagnosis, evidence: dict) -> list[str]:
    """Return the supporting_evidence paths that do not exist in the evidence."""
    return [p for p in diagnosis.supporting_evidence if not resolve_path(evidence, p)[0]]


def _diff_cents(recon: dict) -> int:
    return abs(recon.get("raw_sum_cents", 0) - recon.get("processed_sum_cents", 0))


def _finding_codes(evidence: dict) -> set[str]:
    recon = evidence.get("reconciliation") or {}
    return {f.get("code") for f in recon.get("findings", []) if isinstance(f, dict)}


# --- Rules-based diagnoser ----------------------------------------------------


def diagnose_with_rules(evidence: dict) -> InvestigationResult:
    """Deterministic diagnosis template per scenario. Works with no API key."""
    d = _rules(evidence)
    unsupported = verify_claims(d, evidence)
    return InvestigationResult(
        **d.model_dump(), method="rules", verified=not unsupported, unsupported_claims=unsupported
    )


def _rules(ev: dict) -> Diagnosis:  # noqa: C901 - one branch per scenario is the point
    if not isinstance(ev, dict) or not ev:
        return Diagnosis(
            likely_cause="insufficient_evidence",
            explanation="No evidence was recorded for this incident, so no cause can be proposed.",
            confidence="low",
            uncertainty="Everything. Re-run the pipeline stage with logging enabled.",
            supporting_evidence=[],
            suggested_next_steps=["Confirm the incident has a run_id and re-run reconciliation."],
        )

    # Schema failure at load_raw: nothing was loaded.
    if ev.get("missing_fields") or ev.get("unexpected_fields"):
        missing, extra = ev.get("missing_fields", []), ev.get("unexpected_fields", [])
        renamed = f"{missing[0]} -> {extra[0]}" if missing and extra else ", ".join(missing + extra)
        return Diagnosis(
            likely_cause="upstream_schema_change",
            explanation=(
                f"Ingestion rejected every row because required field(s) {missing} were absent and "
                f"unexpected field(s) {extra} were present. This pattern ({renamed}) matches an "
                "upstream rename of a required field. Nothing was loaded, so downstream tables are "
                "stale rather than wrong."
            ),
            confidence="high" if missing and extra else "medium",
            uncertainty="Whether the rename is intentional (new contract) or an upstream bug.",
            supporting_evidence=["missing_fields", "unexpected_fields", "rows_rejected", "rows_loaded"],
            suggested_next_steps=[
                "Confirm the field rename with the source team before changing the contract.",
                "If intentional, add a versioned mapping in load_raw and replay the batch.",
                "If accidental, request a corrected extract and replay.",
            ],
        )

    recon = ev.get("reconciliation")
    proc = ev.get("process_summary") or {}
    if not isinstance(recon, dict):
        return Diagnosis(
            likely_cause="insufficient_evidence",
            explanation="The incident has no reconciliation snapshot and no schema errors.",
            confidence="low",
            uncertainty="Which stage failed and whether any data is wrong.",
            supporting_evidence=["run_id", "stage"],
            suggested_next_steps=["Re-run reconciliation for the batch and re-open the incident."],
        )

    codes = _finding_codes(ev)
    rejected = proc.get("duplicates_rejected") or []

    if "incomplete_raw_load" in codes:
        return Diagnosis(
            likely_cause="source_extract_incomplete",
            explanation=(
                f"The source promised {recon.get('expected_count')} records but only "
                f"{recon.get('raw_count')} reached raw. The shortfall exists before the transformation "
                "ran, which points at the extract or the ingestion step, not at process_batch."
            ),
            confidence="medium" if "missing_records" in codes else "high",
            uncertainty="Whether the extract was truncated upstream or ingestion stopped early.",
            supporting_evidence=["reconciliation.expected_count", "reconciliation.raw_count"],
            suggested_next_steps=[
                "Compare the source manifest row count with the file actually delivered.",
                "Check the load_raw run for a partial failure before replaying.",
            ],
        )

    if "duplicate_records" in codes:
        return Diagnosis(
            likely_cause="duplicate_rows_stored",
            explanation=(
                f"{recon.get('duplicate_count')} source IDs exist more than once in processed. The "
                "unique constraint should make this impossible, so either it is missing or rows were "
                "written outside the normal path."
            ),
            confidence="high",
            uncertainty="How the constraint was bypassed.",
            supporting_evidence=["reconciliation.duplicate_count", "reconciliation.duplicate_ids"],
            suggested_next_steps=[
                "Verify the (batch_id, source_id) unique constraint exists on transactions_processed.",
                "Identify the writer that bypassed process_batch before deleting duplicates.",
            ],
        )

    if "missing_records" in codes:
        attempted, raw_count = proc.get("rows_attempted"), recon.get("raw_count")
        dropped_before_insert = attempted is not None and raw_count is not None and attempted < raw_count
        return Diagnosis(
            likely_cause="transformation_dropped_records",
            explanation=(
                f"{recon.get('missing_count')} raw transactions have no processed counterpart and the "
                f"totals differ by {_diff_cents(recon)} cents. "
                + (
                    f"process_batch attempted only {attempted} of {raw_count} rows, so the rows were "
                    "filtered out inside the transformation rather than rejected by the database."
                    if dropped_before_insert
                    else "The process stage attempted every raw row, so inserts failed or were lost."
                )
            ),
            confidence="high" if dropped_before_insert else "medium",
            uncertainty="Which filter or condition in the transformation excluded these rows.",
            supporting_evidence=[
                "reconciliation.missing_count",
                "reconciliation.missing_ids",
                "process_summary.rows_attempted",
                "reconciliation.raw_count",
            ],
            suggested_next_steps=[
                "Inspect the listed missing_ids in raw for a shared attribute (status, time, amount).",
                "Propose a replay of this batch; the unique constraint makes it safe to re-run.",
            ],
        )

    if "unexpected_records" in codes:
        return Diagnosis(
            likely_cause="processed_contains_foreign_rows",
            explanation=(
                f"{recon.get('unexpected_count')} processed rows have no raw counterpart in this batch. "
                "They came from another batch or were inserted outside the pipeline."
            ),
            confidence="medium",
            uncertainty="Where the foreign rows originated.",
            supporting_evidence=["reconciliation.unexpected_count", "reconciliation.unexpected_ids"],
            suggested_next_steps=["Look up the unexpected_ids in other batches before removing them."],
        )

    if "total_mismatch" in codes:
        return Diagnosis(
            likely_cause="amount_altered_in_transform",
            explanation=(
                "Every raw ID is present exactly once in processed, yet the cents totals differ. "
                "The transformation changed amounts (rounding, currency, or sign) rather than rows."
            ),
            confidence="medium",
            uncertainty="Which rows changed; a per-row diff is needed.",
            supporting_evidence=["reconciliation.raw_sum_cents", "reconciliation.processed_sum_cents"],
            suggested_next_steps=["Diff amount_cents per source_id between raw and processed."],
        )

    if "window_mismatch" in codes:
        return Diagnosis(
            likely_cause="wrong_reporting_window",
            explanation="Processed rows fall outside the batch business date; the window filter is wrong.",
            confidence="medium",
            uncertainty="Whether the batch label or the row timestamps are at fault.",
            supporting_evidence=["reconciliation.business_date", "reconciliation.findings"],
            suggested_next_steps=["Check time-zone handling in the window filter."],
        )

    if "status_inconsistent" in codes:
        return Diagnosis(
            likely_cause="status_filter_mismatch",
            explanation="Processed contains non-completed rows; revenue must count completed only.",
            confidence="medium",
            uncertainty="Whether raw statuses changed after load.",
            supporting_evidence=["reconciliation.findings"],
            suggested_next_steps=["Apply the status filter in process_batch and replay."],
        )

    if rejected:
        return Diagnosis(
            likely_cause="duplicate_source_rows_blocked",
            explanation=(
                f"The transformation attempted {len(rejected)} duplicate inserts and the unique "
                f"constraint rejected all of them; processed holds {recon.get('processed_count')} rows "
                "with zero duplicates. Tables are intact but the upstream feed re-sent records."
            ),
            confidence="high",
            uncertainty="Why the feed re-sent those IDs.",
            supporting_evidence=[
                "process_summary.duplicates_rejected",
                "reconciliation.duplicate_count",
                "reconciliation.processed_count",
            ],
            suggested_next_steps=[
                "Ask the source team whether the re-sent IDs are retries or a bug.",
                "No recovery needed; keep the incident open as a warning for the audit trail.",
            ],
        )

    return Diagnosis(
        likely_cause="no_fault",
        explanation="Reconciliation passed and the process stage reported no rejections.",
        confidence="high",
        uncertainty="None from this evidence.",
        supporting_evidence=["reconciliation.passed"],
        suggested_next_steps=["Close the incident as a false alarm if one was opened."],
    )


# --- Optional Claude diagnoser ------------------------------------------------

SYSTEM_PROMPT = f"""You are a read-only data-pipeline incident investigator.

You will receive one incident's evidence as JSON. Rules:
- Use ONLY the evidence provided. Do not assume facts that are not in it.
- Choose likely_cause from exactly this list: {", ".join(CAUSES)}.
- supporting_evidence must be dotted paths into the evidence JSON (e.g. reconciliation.missing_count,
  process_summary.rows_attempted, missing_fields). Only cite paths that exist.
- You cannot run queries, modify data, or trigger recovery. suggested_next_steps are for a human.
- State what the evidence cannot establish in uncertainty. Prefer medium or low confidence when
  more than one cause fits.
"""


def diagnose_with_claude(evidence: dict, model: str) -> InvestigationResult:
    """Ask Claude for a structured diagnosis. Falls back to rules on any failure."""
    import json

    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        return _fallback(evidence, f"anthropic SDK not installed: {exc}")

    client = anthropic.Anthropic()
    try:
        response = client.messages.parse(
            model=model,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(evidence, default=str, sort_keys=True)}],
            output_format=Diagnosis,
        )
    except anthropic.AuthenticationError as exc:
        return _fallback(evidence, f"authentication failed: {exc.message}")
    except anthropic.RateLimitError as exc:
        return _fallback(evidence, f"rate limited: {exc.message}")
    except anthropic.APIStatusError as exc:
        return _fallback(evidence, f"API error {exc.status_code}: {exc.message}")
    except anthropic.APIConnectionError as exc:
        return _fallback(evidence, f"connection error: {exc}")

    if response.stop_reason == "refusal":
        detail = response.stop_details.explanation if response.stop_details else "no explanation"
        return _fallback(evidence, f"model refused: {detail}")
    if response.parsed_output is None:
        return _fallback(evidence, f"no structured output (stop_reason={response.stop_reason})")

    diagnosis: Diagnosis = response.parsed_output
    unsupported = verify_claims(diagnosis, evidence)
    if unsupported:
        log.warning("LLM cited evidence paths that do not exist: %s", unsupported)
    return InvestigationResult(
        **diagnosis.model_dump(),
        method="llm",
        model=model,
        verified=not unsupported,
        unsupported_claims=unsupported,
    )


def _fallback(evidence: dict, reason: str) -> InvestigationResult:
    log.warning("LLM investigation unavailable (%s); using rules", reason)
    result = diagnose_with_rules(evidence)
    result.fallback_reason = reason
    return result


# --- Entry point --------------------------------------------------------------


def investigate(evidence: dict, api_key: str, model: str, method: str = "auto") -> InvestigationResult:
    """method='rules' forces the deterministic path; 'auto' uses Claude when a key is configured."""
    if method == "rules" or not api_key:
        result = diagnose_with_rules(evidence)
        if method != "rules":
            result.fallback_reason = "no API key configured"
        return result
    return diagnose_with_claude(evidence, model)
