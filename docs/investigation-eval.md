# Investigator evaluation

Generated 2026-10-27 by `scripts/evaluate_investigator.py`.

12 labeled cases: 4 produced by the real scenario runner (expected cause = injected fault), 8 hand-built to cover situations the demo cannot produce, including ambiguous and empty evidence.

These numbers describe this synthetic set only. They say nothing about real incidents. The rules diagnoser was written against these same scenarios, so its score is a regression check, not a measurement; the LLM column is the only independent result.

| Case | Source | Expected | Rules | Conf. | Correct |
|---|---|---|---|---|---|
| scenario:missing | injected | `transformation_dropped_records` | `transformation_dropped_records` | high | yes |
| scenario:duplicate | injected | `duplicate_source_rows_blocked` | `duplicate_source_rows_blocked` | high | yes |
| scenario:schema | injected | `upstream_schema_change` | `upstream_schema_change` | high | yes |
| scenario:clean | injected | `no_fault` | `no_fault` | high | yes |
| manual:amount_altered | hand-built | `amount_altered_in_transform` | `amount_altered_in_transform` | medium | yes |
| manual:foreign_rows | hand-built | `processed_contains_foreign_rows` | `processed_contains_foreign_rows` | medium | yes |
| manual:extract_incomplete | hand-built | `source_extract_incomplete` | `source_extract_incomplete` | high | yes |
| manual:duplicates_actually_stored | hand-built | `duplicate_rows_stored` | `duplicate_rows_stored` | high | yes |
| manual:ambiguous_missing_plus_duplicates | hand-built (ambiguous) | `transformation_dropped_records` | `transformation_dropped_records` | medium | yes |
| manual:wrong_window | hand-built | `wrong_reporting_window` | `wrong_reporting_window` | medium | yes |
| manual:empty_evidence | hand-built (ambiguous) | `insufficient_evidence` | `insufficient_evidence` | low | yes |
| manual:no_reconciliation_snapshot | hand-built (ambiguous) | `insufficient_evidence` | `insufficient_evidence` | low | yes |

**Rules diagnosis accuracy:** 12/12 = 100%

## Incorrect or unsupported diagnoses

None on this set.
