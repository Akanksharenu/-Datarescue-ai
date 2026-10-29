import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { href } from "../hooks/useHashRoute";
import { when } from "../lib/format";
import { Card, Empty, ErrorBox, Loading, StatusBadge } from "../components/ui";

export function IncidentsPage() {
  const incidents = useAsync(() => api.incidents());

  return (
    <>
      <h2>Incidents</h2>
      <Card
        title="Detected by reconciliation, newest first"
        actions={
          <button type="button" className="btn btn-small btn-secondary" onClick={() => void incidents.reload()}>
            Refresh
          </button>
        }
      >
        {incidents.status === "loading" && !incidents.data && <Loading what="incidents" />}
        {incidents.status === "error" && (
          <ErrorBox message={incidents.error} onRetry={() => void incidents.reload()} />
        )}
        {incidents.data && incidents.data.length === 0 && (
          <Empty>
            No incidents. A clean batch produces none; run <code>missing</code>, <code>duplicate</code> or{" "}
            <code>schema</code> from <a href={href.demo}>Demo control</a>.
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
                <th>Run</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {incidents.data.map((i) => (
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
                  <td>{i.run_id ? `#${i.run_id}` : "-"}</td>
                  <td>{when(i.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
