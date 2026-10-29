import { useEffect, useState } from "react";

/**
 * Minimal hash router: `#/incidents/3` -> ["incidents", "3"]. Hash routing needs no server
 * rewrite rules, so the built dashboard can be served from any static host on Day 6.
 */
export type Route =
  | { page: "overview" }
  | { page: "runs" }
  | { page: "incidents" }
  | { page: "incident"; id: number }
  | { page: "demo" };

export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  switch (parts[0]) {
    case "runs":
      return { page: "runs" };
    case "incidents": {
      const id = Number(parts[1]);
      return parts[1] && Number.isInteger(id) ? { page: "incident", id } : { page: "incidents" };
    }
    case "demo":
      return { page: "demo" };
    default:
      return { page: "overview" };
  }
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export const href = {
  overview: "#/",
  runs: "#/runs",
  incidents: "#/incidents",
  incident: (id: number) => `#/incidents/${id}`,
  demo: "#/demo",
};
