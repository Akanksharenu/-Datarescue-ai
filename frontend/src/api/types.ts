/**
 * TypeScript mirrors of backend/app/schemas.py. If a field changes there, change it here.
 * Money is always integer cents; the UI formats it, it never does arithmetic on floats.
 */

export type Scenario = "clean" | "missing" | "duplicate" | "schema";

export type IncidentType =
  | "schema_mismatch"
  | "incomplete_raw_load"
  | "missing_records"
  | "unexpected_records"
  | "duplicate_records"
  | "total_mismatch"
  | "window_mismatch"
  | "status_inconsistent";

export type IncidentStatus = "open" | "recovering" | "resolved";
export type RecoveryStatus = "proposed" | "approved" | "rejected" | "executed" | "failed";

export interface Health {
  status: string;
}

export interface RunSummary {
  id: number;
  batch_id: string;
  scenario: string;
  stage: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  error: string | null;
  summary: Record<string, unknown>;
}

export interface IncidentSummary {
  id: number;
  batch_id: string;
  run_id: number | null;
  type: IncidentType;
  severity: "critical" | "warning" | "info" | string;
  status: IncidentStatus | string;
  created_at: string;
}

export interface Finding {
  code: string;
  severity: string;
  message: string;
  details: Record<string, unknown>;
}

export interface Reconciliation {
  batch_id: string;
  business_date: string;
  expected_count: number;
  expected_sum_cents: number;
  raw_count: number;
  processed_count: number;
  raw_sum_cents: number;
  processed_sum_cents: number;
  missing_count: number;
  unexpected_count: number;
  duplicate_count: number;
  passed: boolean;
  findings: Finding[];
  // Present in incident evidence (the dataclass dump), absent from the /reconciliation route.
  missing_ids?: string[];
  unexpected_ids?: string[];
  duplicate_ids?: string[];
}

export interface LineageEdge {
  from: string;
  to: string;
  transform: string;
}

export interface LineageImpact {
  path: string[];
  edges: LineageEdge[];
  failed_step: string;
  affected_datasets: string[];
  at_risk_datasets: string[];
  intact_datasets: string[];
  note: string;
}

/** Evidence is a JSON snapshot; keys differ by incident type, so most are optional. */
export interface Evidence {
  simulated: boolean;
  batch_id: string;
  business_date: string;
  run_id: number | null;
  stage: string | null;
  expected_count: number;
  expected_sum_cents: number;
  reconciliation?: Reconciliation;
  process_summary?: Record<string, unknown> | null;
  duplicate_attempts?: string[];
  duplicates_stored?: string[];
  rows_received?: number;
  rows_loaded?: number;
  rows_rejected?: number;
  missing_fields?: string[];
  unexpected_fields?: string[];
  sample_errors?: Record<string, unknown>[];
  error?: string;
  lineage?: LineageImpact;
  [key: string]: unknown;
}

export interface Investigation {
  id: number;
  incident_id: number;
  method: "rules" | "llm";
  model: string | null;
  likely_cause: string;
  explanation: string;
  confidence: "high" | "medium" | "low";
  uncertainty: string;
  supporting_evidence: string[];
  suggested_next_steps: string[];
  verified: boolean;
  unsupported_claims: string[];
  fallback_reason: string | null;
  disclaimer: string;
  created_at: string;
}

export interface IncidentDetail extends IncidentSummary {
  evidence: Evidence;
  lineage: LineageImpact | null;
  investigations: Investigation[];
}

export interface Check {
  name: string;
  passed: boolean;
  detail: string;
}

export interface RecoveryProposal {
  simulated: boolean;
  batch_id: string;
  incident_type: string;
  action: string;
  description: string;
  expected_inserts: number;
  expected_updates: number;
  expected_processed_count_after: number;
  expected_processed_sum_cents_after: number;
  before: Reconciliation;
  preconditions: Check[];
  preconditions_met: boolean;
}

export interface Execution {
  run_id: number;
  at: string;
  rows_attempted: number;
  rows_inserted: number;
  processed_before: number;
  processed_after: number;
}

export interface RecoveryProof {
  simulated: boolean;
  status: "verified" | "failed";
  batch_id: string;
  action: string;
  approval: { approved_by: string | null; approved_at: string | null };
  before: { processed_count: number; processed_sum_cents: number; missing_count: number };
  after: { processed_count: number; processed_sum_cents: number; missing_count: number };
  rows_inserted_this_run: number;
  checks: Check[];
  executions: Execution[];
  verified_at: string;
}

export interface RefusedAttempt {
  at: string;
  reason: string;
  run_id: number | null;
}

/** `result` holds the proof after execution, the rejection after a reject, or refused attempts. */
export type RecoveryResult =
  | (RecoveryProof & { refused_attempts?: RefusedAttempt[] })
  | { rejected_by: string; reason: string; at: string; refused_attempts?: RefusedAttempt[] }
  | { refused_attempts: RefusedAttempt[] };

export interface RecoveryRequest {
  id: number;
  incident_id: number;
  action: string;
  status: RecoveryStatus | string;
  proposal: RecoveryProposal;
  approved_by: string | null;
  approved_at: string | null;
  executed_at: string | null;
  result: RecoveryResult | null;
  created_at: string;
}

export interface ScenarioResult {
  simulated: boolean;
  scenario: Scenario;
  batch_id: string;
  run_ids: number[];
  incident_id: number | null;
  reconciliation: Reconciliation | null;
}

export interface SeedResult {
  simulated: boolean;
  seed: number;
  transactions: number;
  expected_sum_cents: number;
  clean: ScenarioResult;
}

export interface LineageGraph {
  path: string[];
  edges: LineageEdge[];
}

export function isProof(result: RecoveryResult | null): result is RecoveryProof {
  return result !== null && "checks" in result && Array.isArray(result.checks);
}

export function isRejection(
  result: RecoveryResult | null,
): result is { rejected_by: string; reason: string; at: string } {
  return result !== null && "rejected_by" in result;
}
