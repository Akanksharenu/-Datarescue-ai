import { API_URL, api } from "./api/client";
import { useAsync } from "./hooks/useAsync";
import { href, useHashRoute } from "./hooks/useHashRoute";
import { DemoControlPage } from "./pages/DemoControl";
import { IncidentDetailPage } from "./pages/IncidentDetail";
import { IncidentsPage } from "./pages/Incidents";
import { OverviewPage } from "./pages/Overview";
import { PipelineRunsPage } from "./pages/PipelineRuns";

const NAV: { label: string; to: string; match: string[] }[] = [
  { label: "Overview", to: href.overview, match: ["overview"] },
  { label: "Pipeline runs", to: href.runs, match: ["runs"] },
  { label: "Incidents", to: href.incidents, match: ["incidents", "incident"] },
  { label: "Demo control", to: href.demo, match: ["demo"] },
];

export default function App() {
  const route = useHashRoute();
  const health = useAsync(() => api.health());

  return (
    <>
      <div className="banner">
        SIMULATED DATA. This is a six-day learning build; nothing here is a real customer transaction and no
        result represents real customer impact.
      </div>
      <header className="topbar">
        <h1>DataRescue AI</h1>
        <nav>
          {NAV.map((n) => (
            <a key={n.to} href={n.to} className={n.match.includes(route.page) ? "active" : ""}>
              {n.label}
            </a>
          ))}
        </nav>
        <span className="health">
          Backend {API_URL}:{" "}
          {health.status === "success" ? (
            <span className="check-pass">ok</span>
          ) : health.status === "error" ? (
            <span className="check-fail" title={health.error}>
              unreachable
            </span>
          ) : (
            "checking..."
          )}
        </span>
      </header>
      <main>
        {route.page === "overview" && <OverviewPage />}
        {route.page === "runs" && <PipelineRunsPage />}
        {route.page === "incidents" && <IncidentsPage />}
        {route.page === "incident" && <IncidentDetailPage id={route.id} />}
        {route.page === "demo" && <DemoControlPage />}
      </main>
      <footer>DataRescue AI v0.1 · detect → investigate → approve → recover → verify · simulated data only</footer>
    </>
  );
}
