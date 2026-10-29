import { useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { Check, Evidence, IncidentDetail, Investigation, RecoveryRequest } from "../api/types";
import { isProof, isRejection } from "../api/types";
import { LineageView } from "../components/Lineage";
import { Badge, Card, Empty, ErrorBox, IdList, JsonBlock, KeyValue, Loading, StatusBadge } from "../components/ui";
import { useAction, useAsync } from "../hooks/useAsync";
import { href } from "../hooks/useHashRoute";
import { cents, count, label, when } from "../lib/format";

export function IncidentDetailPage({ id }: { id: number }) {
  const incident = useAsync(() => api.incident(id), [id]);
  const recovery = useAsync(async () => (await api.recoveryRequests()).filter((r) => r.incident_id === id), [id]);

  const reloadAll = () => {
    void incident.reload();
    void recovery.reload();
  };

  if (incident.status === "loading" && !incident.data) return <Loading what={`incident #${id}`} />;
  if (incident.status === "error" && !incident.data) {
    return (
      <>
        <h2>Incident #{id}</h2>
        <ErrorBox message={incident.error} onRetry={reloadAll} />
        <p>
          <a href={href.incidents}>Back to incidents</a>
        </p>
      </>
    );
  }
  const inc = incident.data!;

  return (
    <>
      <p>
        <a href={href.incidents}>&larr; All incidents</a>
      </p>
      <h2>
        Incident #{inc.id}: {label(inc.type)} <StatusBadge value={inc.severity} /> <StatusBadge value={inc.status} />
      </h2>
      {incident.status === "error" && <ErrorBox message={incident.error} onRetry={reloadAll} />}

      <div className="grid grid-2">
        <EvidenceCard incident={inc} />
        <Card title="Lineage impact">
          {inc.lineage ? <LineageView impact={inc.lineage} /> : <Empty>No lineage recorded.</Empty>}
        </Card>
      </div>

      <InvestigationCard incident={inc} onChange={() => void incident.reload()} />
      <RecoveryCard
        incident={inc}
        requests={recovery.data ?? []}
        loading={recovery.status === "loading" && !recovery.data}
        error={recovery.status === "error" ? recovery.error : null}
        onChange={reloadAll}
      />
    </>
  );
}

/* ---------------------------------------------------------------- evidence */

function EvidenceCard({ incident }: { incident: IncidentDetail }) {
  const e: Evidence = incident.evidence;
  const r = e.reconciliation;
  const rows: [string, ReactNode][] = [
    ["Batch", <code key="b">{e.batch_id}</code>],
    ["Business date", e.business_date],
    ["Failed stage", e.stage ? <code key="s">{e.stage}</code> : "-"],
    ["Pipeline run", e.run_id ? `#${e.run_id}` : "-"],
    ["Expected rows", count(e.expected_count)],
    ["Expected total", cents(e.expected_sum_cents)],
  ];

  if (incident.type === "schema_mismatch") {
    rows.push(
      ["Rows received", count(e.rows_received)],
      ["Rows loaded", count(e.rows_loaded)],
      ["Rows rejected", count(e.rows_rejected)],
      ["Missing fields", <IdList key="mf" ids={e.missing_fields} />],
      ["Unexpected fields", <IdList key="uf" ids={e.unexpected_fields} />],
    );
  }
  if (r) {
    rows.push(
      ["Raw rows", count(r.raw_count)],
      ["Processed rows", count(r.processed_count)],
      ["Raw total", cents(r.raw_sum_cents)],
      ["Processed total", cents(r.processed_sum_cents)],
      ["Shortfall", cents(r.raw_sum_cents - r.processed_sum_cents)],
      ["Missing IDs", <IdList key="mi" ids={r.missing_ids} />],
      ["Unexpected IDs", <IdList key="ui" ids={r.unexpected_ids} />],
      ["Duplicates stored", <IdList key="di" ids={r.duplicate_ids} />],
    );
  }
  if (e.duplicate_attempts) {
    rows.push(["Duplicate attempts blocked", <IdList key="da" ids={e.duplicate_attempts} />]);
  }

  return (
    <Card title="Evidence (immutable snapshot)">
      <KeyValue rows={rows} />
      {r && r.findings.length > 0 && (
        <>
          <h3 style={{ fontSize: 14, margin: "12px 0 4px" }}>Findings</h3>
          <ul className="checks">
            {r.findings.map((f) => (
              <li key={f.code}>
                <span className="check-fail">!</span>
                <span>
                  <code>{f.code}</code> <StatusBadge value={f.severity} />
                </span>
                <span>{f.message}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {e.error && <p className="check-fail">{e.error}</p>}
      <JsonBlock value={incident.evidence} summary="Full evidence JSON" />
    </Card>
  );
}

/* ----------------------------------------------------------- investigation */

function InvestigationCard({ incident, onChange }: { incident: IncidentDetail; onChange: () => void }) {
  const investigate = useAction(async (method: "auto" | "rules") => {
    const r = await api.investigate(incident.id, method);
    onChange();
    return r;
  });

  return (
    <Card
      title="Investigation (read-only suggestion)"
      actions={
        <>
          <button type="button" className="btn btn-small" disabled={investigate.busy} onClick={() => void investigate.invoke("auto")}>
            {investigate.busy ? "Investigating..." : "Investigate (auto)"}
          </button>
          <button type="button" className="btn btn-small btn-secondary" disabled={investigate.busy} onClick={() => void investigate.invoke("rules")}>
            Rules only
          </button>
        </>
      }
    >
      <p className="muted" style={{ marginTop: 0 }}>
        "Auto" uses Claude when the backend has an API key and falls back to rules otherwise; the result says
        which ran. The investigator reads the evidence JSON only and cannot change any data.
      </p>
      {investigate.error && <ErrorBox message={investigate.error} />}
      {incident.investigations.length === 0 && <Empty>No investigation yet.</Empty>}
      {incident.investigations.map((inv) => (
        <InvestigationView key={inv.id} inv={inv} />
      ))}
    </Card>
  );
}

function InvestigationView({ inv }: { inv: Investigation }) {
  return (
    <div className="investigation">
      <h3>
        {label(inv.likely_cause)} <Badge kind={inv.method === "llm" ? "info" : "muted"}>{inv.method === "llm" ? `LLM: ${inv.model}` : "rules"}</Badge>{" "}
        <Badge kind={inv.confidence === "high" ? "good" : inv.confidence === "medium" ? "warn" : "bad"}>
          {inv.confidence} confidence
        </Badge>{" "}
        {inv.verified ? <Badge kind="good">claims verified</Badge> : <Badge kind="bad">unverified claims</Badge>}
      </h3>
      <p>{inv.explanation}</p>
      {inv.fallback_reason && (
        <p className="notice notice-warn">Fell back to rules: {inv.fallback_reason}</p>
      )}
      <KeyValue
        rows={[
          ["What it cannot tell", inv.uncertainty],
          [
            "Supporting evidence",
            <ul key="se">
              {inv.supporting_evidence.map((p) => (
                <li key={p}>
                  <code>{p}</code>
                </li>
              ))}
            </ul>,
          ],
          [
            "Next steps",
            <ul key="ns">
              {inv.suggested_next_steps.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>,
          ],
          ...(inv.unsupported_claims.length > 0
            ? ([
                [
                  "Unsupported claims",
                  <ul key="uc" className="check-fail">
                    {inv.unsupported_claims.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>,
                ],
              ] as [string, ReactNode][])
            : []),
          ["Recorded", when(inv.created_at)],
        ]}
      />
      <p className="disclaimer">{inv.disclaimer}</p>
    </div>
  );
}

/* ---------------------------------------------------------------- recovery */

function RecoveryCard({
  incident,
  requests,
  loading,
  error,
  onChange,
}: {
  incident: IncidentDetail;
  requests: RecoveryRequest[];
  loading: boolean;
  error: string | null;
  onChange: () => void;
}) {
  const propose = useAction(async () => {
    const r = await api.proposeRecovery(incident.id);
    onChange();
    return r;
  });
  const active = requests.find((r) => r.status === "proposed" || r.status === "approved" || r.status === "executed");

  return (
    <Card
      title="Recovery (approval required)"
      actions={
        !active &&
        incident.status !== "resolved" && (
          <button type="button" className="btn btn-small" disabled={propose.busy} onClick={() => void propose.invoke()}>
            {propose.busy ? "Proposing..." : "Propose recovery"}
          </button>
        )
      }
    >
      <p className="muted" style={{ marginTop: 0 }}>
        Three separate steps, each recorded: propose a replay, a named person approves it, then execute. Executing
        without approval is refused and logged as a failed run. Re-executing inserts nothing.
      </p>
      {propose.error && <ErrorBox message={propose.error} />}
      {error && <ErrorBox message={error} onRetry={onChange} />}
      {loading && <Loading what="recovery requests" />}
      {!loading && requests.length === 0 && (
        <Empty>
          No recovery request yet.{" "}
          {incident.status === "resolved" ? "The incident is already resolved." : "Click Propose recovery to build one from the live data."}
        </Empty>
      )}
      {requests.map((r) => (
        <RecoveryRequestView key={r.id} request={r} onChange={onChange} />
      ))}
    </Card>
  );
}

function RecoveryRequestView({ request, onChange }: { request: RecoveryRequest; onChange: () => void }) {
  const [approver, setApprover] = useState("");
  const [reason, setReason] = useState("");
  const p = request.proposal;

  const approve = useAction(async () => {
    await api.approveRecovery(request.id, approver);
    onChange();
  });
  const reject = useAction(async () => {
    await api.rejectRecovery(request.id, approver || "reviewer", reason || "no reason given");
    onChange();
  });
  const execute = useAction(async () => {
    await api.executeRecovery(request.id);
    onChange();
  });
  const busy = approve.busy || reject.busy || execute.busy;
  const result = request.result;

  return (
    <div className="investigation">
      <h3>
        Request #{request.id}: {label(request.action)} <StatusBadge value={request.status} />
      </h3>

      <KeyValue
        rows={[
          ["Plan", p.description],
          ["Expected inserts", count(p.expected_inserts)],
          ["Expected updates", count(p.expected_updates)],
          ["Processed rows after", `${count(p.before.processed_count)} -> ${count(p.expected_processed_count_after)}`],
          ["Processed total after", `${cents(p.before.processed_sum_cents)} -> ${cents(p.expected_processed_sum_cents_after)}`],
          ["Preconditions", <Checks key="pc" checks={p.preconditions} />],
          ["Proposed", when(request.created_at)],
          ...(request.approved_by ? ([["Approved by", `${request.approved_by} at ${when(request.approved_at)}`]] as [string, ReactNode][]) : []),
        ]}
      />

      {request.status === "proposed" && (
        <div className="row">
          <input type="text" placeholder="Your name (approver)" value={approver} onChange={(e) => setApprover(e.target.value)} />
          <button type="button" className="btn" disabled={busy || !approver.trim() || !p.preconditions_met} onClick={() => void approve.invoke()}>
            {approve.busy ? "Approving..." : "Approve"}
          </button>
          <input type="text" placeholder="Rejection reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          <button type="button" className="btn btn-danger" disabled={busy} onClick={() => void reject.invoke()}>
            Reject
          </button>
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => void execute.invoke()} title="Should be refused: not approved">
            Try execute without approval
          </button>
        </div>
      )}
      {request.status === "proposed" && !p.preconditions_met && (
        <p className="notice notice-warn">Preconditions are not met; approval is disabled.</p>
      )}
      {(request.status === "approved" || request.status === "executed") && (
        <div className="row">
          <button type="button" className="btn" disabled={busy} onClick={() => void execute.invoke()}>
            {execute.busy ? "Replaying..." : request.status === "executed" ? "Execute again (should insert 0)" : "Execute replay"}
          </button>
        </div>
      )}
      {approve.error && <ErrorBox message={approve.error} />}
      {reject.error && <ErrorBox message={reject.error} />}
      {execute.error && <ErrorBox message={execute.error} />}

      {isRejection(result) && (
        <p className="notice notice-warn">
          Rejected by {result.rejected_by} at {when(result.at)}: {result.reason}
        </p>
      )}

      {isProof(result) && (
        <div style={{ marginTop: 12 }}>
          <h3>
            Proof <StatusBadge value={result.status} />
          </h3>
          <KeyValue
            rows={[
              ["Processed rows", `${count(result.before.processed_count)} -> ${count(result.after.processed_count)}`],
              ["Processed total", `${cents(result.before.processed_sum_cents)} -> ${cents(result.after.processed_sum_cents)}`],
              ["Missing rows", `${count(result.before.missing_count)} -> ${count(result.after.missing_count)}`],
              ["Inserted this run", count(result.rows_inserted_this_run)],
              ["Approval", `${result.approval.approved_by} at ${when(result.approval.approved_at)}`],
              ["Revalidation checks", <Checks key="c" checks={result.checks} />],
              [
                "Executions",
                <ul key="ex" style={{ margin: 0, paddingLeft: 18 }}>
                  {result.executions.map((x) => (
                    <li key={x.run_id}>
                      run #{x.run_id} at {when(x.at)}: attempted {count(x.rows_attempted)}, inserted {count(x.rows_inserted)}, processed{" "}
                      {count(x.processed_before)} &rarr; {count(x.processed_after)}
                    </li>
                  ))}
                </ul>,
              ],
              ["Verified at", when(result.verified_at)],
            ]}
          />
        </div>
      )}

      {result && "refused_attempts" in result && result.refused_attempts && result.refused_attempts.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <strong className="check-fail">Refused execution attempts</strong>
          <ul style={{ margin: "4px 0", paddingLeft: 18 }}>
            {result.refused_attempts.map((a, i) => (
              <li key={i}>
                {when(a.at)}: {a.reason} (recorded as run #{a.run_id ?? "?"})
              </li>
            ))}
          </ul>
        </div>
      )}
      <JsonBlock value={request} summary="Full request JSON" />
    </div>
  );
}

function Checks({ checks }: { checks: Check[] }) {
  return (
    <ul className="checks">
      {checks.map((c) => (
        <li key={c.name}>
          <span className={c.passed ? "check-pass" : "check-fail"}>{c.passed ? "✓" : "✗"}</span>
          <code>{c.name}</code>
          <span className="muted">{c.detail}</span>
        </li>
      ))}
    </ul>
  );
}
