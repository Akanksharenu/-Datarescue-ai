import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { href } from "../hooks/useHashRoute";
import { count, when } from "../lib/format";
import { Card, Empty, ErrorBox, Loading, Stat, StatusBadge } from "../components/ui";

export function OverviewPage() {
  const incidents = useAsync(() => api.incidents());
  const runs = useAsync(() => api.pipelineRuns());
  const recovery = useAsync(() => api.recoveryRequests());

  const reload = () => {
    void incidents.reload();
    void runs.reload();
    void recovery.reload();
  };

  const inc = incidents.data ?? [];
  const open = inc.filter((i) => i.status === "open").length;
  const recovering = inc.filter((i) => i.status === "recovering").length;
  const resolved = inc.filter((i) => i.status === "resolved").length;
  const failedRuns = (runs.data ?? []).filter((r) => r.status === "failed").length;
  const awaiting = (recovery.data ?? []).filter((r) => r.status === "proposed").length;

  const anyError = incidents.status === "error" || runs.status === "error" || recovery.status === "error";
  const firstError =
    incidents.status === "error"
      ? incidents.error
      : runs.status === "error"
        ? runs.error
        : recovery.status === "error"
          ? recovery.error
          : "";

  return (
    <>
      <h2>Overview</h2>
      {anyError && <ErrorBox message={firstError} onRetry={reload} />}

      <div className="grid grid-stats" style={{ marginBottom: 16 }}>
        <Stat label="Open incidents" value={incidents.data ? count(open) : "…"} hint="need attention" />
        <Stat label="Recovering" value={incidents.data ? count(recovering) : "…"} hint="approved, awaiting replay" />
        <Stat label="Resolved" value={incidents.data ? count(resolved) : "…"} hint="verified by reconciliation" />
        <Stat label="Failed runs" value={runs.data ? count(failedRuns) : "…"} hint="pipeline stages that errored" />
        <Stat label="Awaiting approval" value={recovery.data ? count(awaiting) : "…"} hint="recovery proposals" />
      </div>

      <Card
        title="Latest incidents"
        actions={
          <>
            <a href={href.incidents}>All incidents</a>
            <button type="button" className="btn btn-small btn-secondary" onClick={reload}>
              Refresh
            </button>
          </>
        }
      >
        {incidents.status === "loading" && !incidents.data && <Loading what="incidents" />}
        {incidents.data && incidents.data.length === 0 && (
          <Empty>
            No incidents yet. Go to <a href={href.demo}>Demo control</a>, seed the data, then run the{" "}
            <code>missing</code> scenario.
          </Empty>
        )}
        {incidents.data && incidents.data.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Batch</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {incidents.data.slice(0, 5).map((i) => (
                <tr key={i.id} className="clickable" onClick={() => (window.location.hash = href.incident(i.id))}>
                  <td>
                    <a href={href.incident(i.id)}>#{i.id}</a>
                  </td>
                  <td>{i.type.replace(/_/g, " ")}</td>
                  <td>
                    <StatusBadge value={i.severity} />
                  </td>
                  <td>
                    <StatusBadge value={i.status} />
                  </td>
                  <td>
                    <code>{i.batch_id}</code>
                  </td>
                  <td>{when(i.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="How this works">
        <p>
          <strong>Detect</strong>: SQL reconciliation compares the source promise, raw rows and processed rows for
          each batch. <strong>Investigate</strong>: a rules engine, or Claude when a key is configured, suggests a
          cause from the stored evidence only. <strong>Approve</strong>: a named person approves a replay proposal.{" "}
          <strong>Recover</strong>: the batch is replayed with idempotent inserts. <strong>Verify</strong>: the same
          SQL checks run again and the incident resolves only if every one passes.
        </p>
        <p className="muted">
          AI output is a suggestion. Correctness is decided by the deterministic checks, never by the model.
        </p>
      </Card>
    </>
  );
}
