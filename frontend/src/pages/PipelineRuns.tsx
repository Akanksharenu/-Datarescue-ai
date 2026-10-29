import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { href } from "../hooks/useHashRoute";
import { count, when } from "../lib/format";
import { Card, Empty, ErrorBox, Loading, StatusBadge } from "../components/ui";
import type { RunSummary } from "../api/types";

function summaryText(run: RunSummary): string {
  const s = run.summary;
  const parts: string[] = [];
  const n = (k: string) => (typeof s[k] === "number" ? (s[k] as number) : undefined);
  if (n("rows_received") !== undefined) parts.push(`${count(n("rows_received"))} received`);
  if (n("rows_loaded") !== undefined) parts.push(`${count(n("rows_loaded"))} loaded`);
  if (n("rows_attempted") !== undefined) parts.push(`${count(n("rows_attempted"))} attempted`);
  if (n("rows_inserted") !== undefined) parts.push(`${count(n("rows_inserted"))} inserted`);
  if (n("rows_rejected") !== undefined) parts.push(`${count(n("rows_rejected"))} rejected`);
  if (Array.isArray(s.duplicates_rejected) && s.duplicates_rejected.length > 0) {
    parts.push(`${s.duplicates_rejected.length} duplicates blocked`);
  }
  if (typeof s.injected_fault === "string") parts.push(`injected: ${s.injected_fault}`);
  if (s.refused === true) parts.push("refused execution");
  return parts.join(" · ");
}

export function PipelineRunsPage() {
  const runs = useAsync(() => api.pipelineRuns());

  return (
    <>
      <h2>Pipeline runs</h2>
      <Card
        title="Every stage execution, newest first"
        actions={
          <button type="button" className="btn btn-small btn-secondary" onClick={() => void runs.reload()}>
            Refresh
          </button>
        }
      >
        {runs.status === "loading" && !runs.data && <Loading what="pipeline runs" />}
        {runs.status === "error" && <ErrorBox message={runs.error} onRetry={() => void runs.reload()} />}
        {runs.data && runs.data.length === 0 && (
          <Empty>
            No runs yet. Seed the demo from <a href={href.demo}>Demo control</a>.
          </Empty>
        )}
        {runs.data && runs.data.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Batch</th>
                <th>Scenario</th>
                <th>Stage</th>
                <th>Status</th>
                <th>Started</th>
                <th>Summary</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.map((r) => (
                <tr key={r.id}>
                  <td>#{r.id}</td>
                  <td>
                    <code>{r.batch_id}</code>
                  </td>
                  <td>{r.scenario}</td>
                  <td>
                    <code>{r.stage}</code>
                  </td>
                  <td>
                    <StatusBadge value={r.status} />
                  </td>
                  <td>{when(r.started_at)}</td>
                  <td>
                    {summaryText(r)}
                    {r.error && (
                      <div className="check-fail" style={{ fontSize: 13 }}>
                        {r.error}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
