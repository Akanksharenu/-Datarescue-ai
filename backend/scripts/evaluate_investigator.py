"""Grade the investigator against labeled incident cases (ticket DR-008).

    python scripts/evaluate_investigator.py            # rules only
    python scripts/evaluate_investigator.py --llm      # also run Claude (needs ANTHROPIC_API_KEY)
    python scripts/evaluate_investigator.py --write    # write docs/investigation-eval.md

Cases 1-4 come from the real scenario runner on a throwaway SQLite database, so their
expected cause is the fault that was actually injected. Cases 5-12 are hand-built evidence
for situations the demo cannot produce, including ambiguous and empty ones.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.config import settings  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.demo import run_scenario  # noqa: E402
from app.services.investigation import diagnose_with_claude, diagnose_with_rules  # noqa: E402

DOCS = Path(__file__).resolve().parents[2] / "docs" / "investigation-eval.md"


def _recon(**overrides) -> dict:
    base = {
        "batch_id": "manual",
        "business_date": "2026-10-26",
        "expected_count": 1000,
        "expected_sum_cents": 25505253,
        "raw_count": 1000,
        "processed_count": 1000,
        "raw_sum_cents": 25505253,
        "processed_sum_cents": 25505253,
        "missing_ids": [],
        "unexpected_ids": [],
        "duplicate_ids": [],
        "missing_count": 0,
        "unexpected_count": 0,
        "duplicate_count": 0,
        "passed": True,
        "findings": [],
    }
    base.update(overrides)
    base["passed"] = not base["findings"]
    return base


def scenario_cases() -> list[dict]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    expected = {
        "missing": "transformation_dropped_records",
        "duplicate": "duplicate_source_rows_blocked",
        "schema": "upstream_schema_change",
    }
    cases = []
    with factory() as session:
        for scenario, cause in expected.items():
            outcome = run_scenario(session, scenario)
            cases.append(
                {
                    "name": f"scenario:{scenario}",
                    "source": "injected",
                    "expected": cause,
                    "evidence": outcome.incident.evidence,
                }
            )
        clean = run_scenario(session, "clean")
        cases.append(
            {
                "name": "scenario:clean",
                "source": "injected",
                "expected": "no_fault",
                "evidence": {
                    "simulated": True,
                    "batch_id": clean.batch_id,
                    "reconciliation": clean.reconciliation.to_dict(),
                    "process_summary": {"duplicates_rejected": [], "rows_attempted": 1000},
                },
            }
        )
    return cases


def manual_cases() -> list[dict]:
    return [
        {
            "name": "manual:amount_altered",
            "source": "hand-built",
            "expected": "amount_altered_in_transform",
            "evidence": {
                "reconciliation": _recon(
                    processed_sum_cents=25505000,
                    findings=[{"code": "total_mismatch", "severity": "critical"}],
                ),
                "process_summary": {"rows_attempted": 1000, "duplicates_rejected": []},
            },
        },
        {
            "name": "manual:foreign_rows",
            "source": "hand-built",
            "expected": "processed_contains_foreign_rows",
            "evidence": {
                "reconciliation": _recon(
                    processed_count=1003,
                    unexpected_ids=["TX999001", "TX999002", "TX999003"],
                    unexpected_count=3,
                    findings=[
                        {"code": "unexpected_records", "severity": "critical"},
                        {"code": "total_mismatch", "severity": "critical"},
                    ],
                ),
            },
        },
        {
            "name": "manual:extract_incomplete",
            "source": "hand-built",
            "expected": "source_extract_incomplete",
            "evidence": {
                "reconciliation": _recon(
                    raw_count=900,
                    processed_count=900,
                    findings=[{"code": "incomplete_raw_load", "severity": "critical"}],
                ),
            },
        },
        {
            "name": "manual:duplicates_actually_stored",
            "source": "hand-built",
            "expected": "duplicate_rows_stored",
            "evidence": {
                "reconciliation": _recon(
                    processed_count=1005,
                    duplicate_ids=["TX000001", "TX000002", "TX000003", "TX000004", "TX000005"],
                    duplicate_count=5,
                    findings=[
                        {"code": "duplicate_records", "severity": "critical"},
                        {"code": "total_mismatch", "severity": "critical"},
                    ],
                ),
            },
        },
        {
            "name": "manual:ambiguous_missing_plus_duplicates",
            "source": "hand-built (ambiguous)",
            "expected": "transformation_dropped_records",
            "evidence": {
                "reconciliation": _recon(
                    processed_count=990,
                    missing_ids=[f"TX{n:06d}" for n in range(1, 11)],
                    missing_count=10,
                    findings=[
                        {"code": "missing_records", "severity": "critical"},
                        {"code": "total_mismatch", "severity": "critical"},
                    ],
                ),
                "process_summary": {"rows_attempted": 1000, "duplicates_rejected": ["TX000500"]},
            },
        },
        {
            "name": "manual:wrong_window",
            "source": "hand-built",
            "expected": "wrong_reporting_window",
            "evidence": {
                "reconciliation": _recon(findings=[{"code": "window_mismatch", "severity": "warning"}]),
            },
        },
        {
            "name": "manual:empty_evidence",
            "source": "hand-built (ambiguous)",
            "expected": "insufficient_evidence",
            "evidence": {},
        },
        {
            "name": "manual:no_reconciliation_snapshot",
            "source": "hand-built (ambiguous)",
            "expected": "insufficient_evidence",
            "evidence": {"run_id": 7, "stage": "process", "batch_id": "x"},
        },
    ]


def grade(cases: list[dict], use_llm: bool) -> list[dict]:
    rows = []
    for case in cases:
        rules = diagnose_with_rules(case["evidence"])
        row = {
            "case": case["name"],
            "source": case["source"],
            "expected": case["expected"],
            "rules": rules.likely_cause,
            "rules_confidence": rules.confidence,
            "rules_correct": rules.likely_cause == case["expected"],
            "rules_unsupported": rules.unsupported_claims,
        }
        if use_llm:
            llm = diagnose_with_claude(case["evidence"], settings.llm_model)
            row.update(
                {
                    "llm": llm.likely_cause,
                    "llm_confidence": llm.confidence,
                    "llm_correct": llm.likely_cause == case["expected"],
                    "llm_unsupported": llm.unsupported_claims,
                    "llm_method": llm.method,
                    "llm_fallback": llm.fallback_reason,
                }
            )
        rows.append(row)
    return rows


def render(rows: list[dict], use_llm: bool) -> str:
    n = len(rows)
    rules_ok = sum(r["rules_correct"] for r in rows)
    lines = [
        "# Investigator evaluation",
        "",
        f"Generated {date.today().isoformat()} by `scripts/evaluate_investigator.py`.",
        "",
        f"{n} labeled cases: 4 produced by the real scenario runner (expected cause = injected fault), "
        "8 hand-built to cover situations the demo cannot produce, including ambiguous and empty evidence.",
        "",
        "These numbers describe this synthetic set only. They say nothing about real incidents. "
        "The rules diagnoser was written against these same scenarios, so its score is a regression "
        "check, not a measurement; the LLM column is the only independent result.",
        "",
        "| Case | Source | Expected | Rules | Conf. | Correct |"
        + (" LLM | Conf. | Correct | Unsupported |" if use_llm else ""),
        "|---|---|---|---|---|---|" + ("---|---|---|---|" if use_llm else ""),
    ]
    for r in rows:
        line = (
            f"| {r['case']} | {r['source']} | `{r['expected']}` | `{r['rules']}` | {r['rules_confidence']} | "
            f"{'yes' if r['rules_correct'] else 'NO'} |"
        )
        if use_llm:
            line += (
                f" `{r.get('llm')}` ({r.get('llm_method')}) | {r.get('llm_confidence')} | "
                f"{'yes' if r.get('llm_correct') else 'NO'} | "
                f"{', '.join(r.get('llm_unsupported', [])) or '-'} |"
            )
        lines.append(line)
    lines += ["", f"**Rules diagnosis accuracy:** {rules_ok}/{n} = {rules_ok / n:.0%}"]
    if use_llm:
        llm_ok = sum(bool(r.get("llm_correct")) for r in rows)
        ran = sum(r.get("llm_method") == "llm" for r in rows)
        lines.append(f"**LLM diagnosis accuracy:** {llm_ok}/{n} = {llm_ok / n:.0%} (model ran on {ran}/{n})")
        bad = [r for r in rows if r.get("llm_unsupported")]
        lines.append(f"**LLM unsupported claims:** {len(bad)} case(s) cited evidence paths that do not exist")
    wrong = [r for r in rows if not r["rules_correct"] or (use_llm and not r.get("llm_correct"))]
    lines += ["", "## Incorrect or unsupported diagnoses", ""]
    if not wrong:
        lines.append("None on this set.")
    for r in wrong:
        lines.append(
            f"- **{r['case']}**: expected `{r['expected']}`, rules said `{r['rules']}`"
            + (f", LLM said `{r.get('llm')}`" if use_llm else "")
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--llm", action="store_true", help="also run the Claude investigator")
    parser.add_argument("--write", action="store_true", help="write docs/investigation-eval.md")
    args = parser.parse_args()

    if args.llm and not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY is not set; --llm would only exercise the rules fallback. Aborting.")
        sys.exit(2)

    rows = grade(scenario_cases() + manual_cases(), args.llm)
    report = render(rows, args.llm)
    print(report)
    if args.write:
        DOCS.write_text(report, encoding="utf-8")
        print(f"Wrote {DOCS}")
    print(json.dumps([r for r in rows if not r["rules_correct"]], indent=2) or "")


if __name__ == "__main__":
    main()
