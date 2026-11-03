import { useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { Scenario, ScenarioResult, SeedResult } from "../api/types";
import { useAction } from "../hooks/useAsync";
import { href } from "../hooks/useHashRoute";
import { cents, count } from "../lib/format";
import { Card, ErrorBox, KeyValue, StatusBadge } from "../components/ui";

const SCENARIOS: { id: Scenario; title: string; what: string }[] = [
  { id: "clean", title: "Clean", what: "1,000 rows load and process with no fault. Expect no incident." },
  { id: "missing", title: "Missing records", what: "The transformation drops 280 of 1,000 rows. Expect a critical incident." },
  { id: "duplicate", title: "Duplicate attempt", what: "40 source IDs are re-sent. The unique constraint blocks them. Expect a warning." },
  { id: "schema", title: "Schema change", what: "The source renames amount_cents to amount. Nothing loads. Expect a critical incident." },
];

export function DemoControlPage() {
  const [seedResult, setSeedResult] = useState<SeedResult | null>(null);
  const [lastRun, setLastRun] = useState<ScenarioResult | null>(null);

  const seed = useAction(async () => {
    const r = await api.seed();
    setSeedResult(r);
    setLastRun(null);
    return r;
  });
  const run = useAction(async (scenario: Scenario) => {
    const r = await api.runScenario(scenario);
    setLastRun(r);
    return r;
  });

  const busy = seed.busy || run.busy;

  return (
    <>
      <h2>Demo control</h2>
      <p className="muted">
        Everything here is simulated. Seeding resets the database and loads a reproducible batch; each scenario
        injects one controlled fault into a copy of that batch.
      </p>

      <Card
        title="Step 1: seed"
        actions={
          <button type="button" className="btn" disabled={busy} onClick={() => void seed.invoke()}>
            {seed.busy ? "Seeding..." : "Reset and seed"}
          </button>
        }
      >
        {seed.error && <ErrorBox message={seed.error} />}
        {seedResult ? (
          <div className="notice notice-good">
            Seeded {count(seedResult.transactions)} transactions (seed {seedResult.seed}), expected total{" "}
            {cents(seedResult.expected_sum_cents)}. Clean batch <code>{seedResult.clean.batch_id}</code> reconciled:{" "}
            {seedResult.clean.reconciliation?.passed ? "passed" : "failed"}.
          </div>
        ) : (
          <p className="muted">Resets every table. Safe to repeat; the data is deterministic.</p>
        )}
      </Card>

      <Card title="Step 2: run a scenario">
        <div className="grid grid-2">
          {SCENARIOS.map((s) => (
            <div key={s.id} className="stat">
              <div className="stat-label">{s.id}</div>
              <div style={{ fontWeight: 600 }}>{s.title}</div>
              <p className="muted" style={{ margin: "4px 0 10px", fontSize: 13 }}>
                {s.what}
              </p>
              <button type="button" className="btn btn-small" disabled={busy} onClick={() => void run.invoke(s.id)}>
                {run.busy ? "Running..." : `Run ${s.id}`}
              </button>
            </div>
          ))}
        </div>
        {run.error && <ErrorBox message={run.error} />}
      </Card>

      {lastRun && (
        <Card title={`Result: ${lastRun.scenario}`}>
          <KeyValue
            rows={[
              ["Batch", <code key="b">{lastRun.batch_id}</code>],
              ["Runs recorded", lastRun.run_ids.map((id) => `#${id}`).join(", ")],
              [
                "Incident",
                lastRun.incident_id ? (
                  <a key="i" href={href.incident(lastRun.incident_id)}>
                    Open incident #{lastRun.incident_id}
                  </a>
                ) : (
                  <StatusBadge key="n" value="none" />
                ),
              ],
              ...(lastRun.reconciliation
                ? ([
                    ["Reconciliation", <StatusBadge key="r" value={lastRun.reconciliation.passed ? "verified" : "failed"} />],
                    ["Raw rows", count(lastRun.reconciliation.raw_count)],
                    ["Processed rows", count(lastRun.reconciliation.processed_count)],
                    ["Raw total", cents(lastRun.reconciliation.raw_sum_cents)],
                    ["Processed total", cents(lastRun.reconciliation.processed_sum_cents)],
                    ["Missing", count(lastRun.reconciliation.missing_count)],
                  ] as [string, ReactNode][])
                : ([["Reconciliation", "not run (nothing was loaded)"]] as [string, ReactNode][])),
            ]}
          />
        </Card>
      )}
    </>
  );
}
