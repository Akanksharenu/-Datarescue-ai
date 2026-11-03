/**
 * Typed HTTP client for the DataRescue backend. One function per route in
 * backend/app/api/routes.py. Errors carry the HTTP status and the backend's `detail`
 * so the UI can show "409: Recovery request 3 is not approved" instead of "Request failed".
 */

import type {
  Health,
  IncidentDetail,
  IncidentSummary,
  Investigation,
  LineageGraph,
  Reconciliation,
  RecoveryRequest,
  RunSummary,
  Scenario,
  ScenarioResult,
  SeedResult,
} from "./types";

export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    });
  } catch (err) {
    throw new ApiError(0, `Cannot reach the backend at ${API_URL}. Is uvicorn running? (${String(err)})`);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail !== undefined) detail = JSON.stringify(body.detail);
    } catch {
      /* body was not JSON; keep statusText */
    }
    throw new ApiError(response.status, `${response.status}: ${detail}`);
  }
  return (await response.json()) as T;
}

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/health"),

  // Demo control (Day 2)
  seed: () => post<SeedResult>("/demo/seed"),
  runScenario: (scenario: Scenario) => post<ScenarioResult>(`/demo/run?scenario=${scenario}`),

  // Observability
  pipelineRuns: () => request<RunSummary[]>("/pipeline-runs"),
  incidents: () => request<IncidentSummary[]>("/incidents"),
  incident: (id: number) => request<IncidentDetail>(`/incidents/${id}`),
  reconciliation: (batchId: string) =>
    request<Reconciliation>(`/batches/${encodeURIComponent(batchId)}/reconciliation`),
  lineage: () => request<LineageGraph>("/lineage"),

  // Investigation (Day 3): read-only on the backend; the UI only asks for a suggestion.
  investigate: (incidentId: number, method: "auto" | "rules" = "auto") =>
    post<Investigation>(`/incidents/${incidentId}/investigate?method=${method}`),

  // Recovery (Day 5): propose -> approve -> execute. Every step is a separate, explicit call.
  proposeRecovery: (incidentId: number) => post<RecoveryRequest>(`/incidents/${incidentId}/recovery`),
  recoveryRequests: () => request<RecoveryRequest[]>("/recovery"),
  recoveryRequest: (id: number) => request<RecoveryRequest>(`/recovery/${id}`),
  approveRecovery: (id: number, approvedBy: string) =>
    post<RecoveryRequest>(`/recovery/${id}/approve`, { approved_by: approvedBy }),
  rejectRecovery: (id: number, rejectedBy: string, reason: string) =>
    post<RecoveryRequest>(`/recovery/${id}/reject`, { rejected_by: rejectedBy, reason }),
  executeRecovery: (id: number) => post<RecoveryRequest>(`/recovery/${id}/execute`),
};
