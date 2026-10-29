import type { LineageImpact } from "../api/types";
import { Badge } from "./ui";

/**
 * Renders the four-node pipeline graph and colors each dataset by the incident's impact:
 * intact (green), at risk (amber, duplicates blocked so nothing corrupted) or affected (red).
 */
export function LineageView({ impact }: { impact: LineageImpact }) {
  const state = (node: string) => {
    if (impact.affected_datasets.includes(node)) return "affected";
    if (impact.at_risk_datasets.includes(node)) return "at-risk";
    return "intact";
  };

  return (
    <div className="lineage">
      <ol className="lineage-path">
        {impact.path.map((node, i) => {
          const edge = impact.edges[i - 1];
          const failed = edge?.transform === impact.failed_step;
          return (
            <li key={node} className="lineage-step">
              {edge && (
                <div className={`lineage-edge ${failed ? "lineage-edge-failed" : ""}`}>
                  <span className="lineage-arrow">&rarr;</span>
                  <code>{edge.transform}</code>
                  {failed && <Badge kind="bad">failed here</Badge>}
                </div>
              )}
              <div className={`lineage-node lineage-${state(node)}`}>
                <div className="lineage-name">{node.replace(/_/g, " ")}</div>
                <div className="lineage-state">{state(node).replace("-", " ")}</div>
              </div>
            </li>
          );
        })}
      </ol>
      <p className="muted">{impact.note}</p>
    </div>
  );
}
