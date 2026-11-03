import type { ReactNode } from "react";

/* Small presentational building blocks shared by every page. */

export function Badge({ kind, children }: { kind: string; children: ReactNode }) {
  return <span className={`badge badge-${kind}`}>{children}</span>;
}

/** Map backend status/severity strings onto a handful of colors. */
export function tone(value: string): string {
  switch (value) {
    case "critical":
    case "failed":
    case "open":
    case "rejected":
      return "bad";
    case "warning":
    case "recovering":
    case "proposed":
    case "medium":
      return "warn";
    case "succeeded":
    case "resolved":
    case "executed":
    case "verified":
    case "approved":
    case "high":
      return "good";
    case "running":
    case "loading":
      return "info";
    default:
      return "muted";
  }
}

export function StatusBadge({ value }: { value: string }) {
  return <Badge kind={tone(value)}>{value.replace(/_/g, " ")}</Badge>;
}

export function Loading({ what = "data" }: { what?: string }) {
  return (
    <p className="state state-loading" role="status">
      Loading {what}...
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="state state-empty">{children}</p>;
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state state-error" role="alert">
      <strong>Something went wrong.</strong> {message}
      {onRetry && (
        <button type="button" className="btn btn-small" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function KeyValue({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="kv">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function JsonBlock({ value, summary = "Raw JSON" }: { value: unknown; summary?: string }) {
  return (
    <details className="json">
      <summary>{summary}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

export function IdList({ ids, max = 12 }: { ids: string[] | undefined; max?: number }) {
  if (!ids || ids.length === 0) return <span className="muted">none</span>;
  const shown = ids.slice(0, max);
  return (
    <span className="ids">
      {shown.join(", ")}
      {ids.length > max && <span className="muted"> and {ids.length - max} more</span>}
    </span>
  );
}
