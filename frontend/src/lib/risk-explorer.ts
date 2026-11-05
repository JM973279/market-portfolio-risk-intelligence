import type { MarketPoint } from "./dashboard-types";
export type RiskMetric = "risk" | "msi";
export function finiteValue(value: number | null | undefined): number | null {
 return typeof value === "number" && Number.isFinite(value) ? value : null;
}
// Exact-date lookup: never substitute another market's date or carry a value forward.
export function observationAt(points: MarketPoint[], day: string): MarketPoint | null {
 return points.find(point => point.date === day) ?? null;
}
export function signalPath(points: MarketPoint[], key: RiskMetric | "threshold", x: (date: string) => number, y: (value: number) => number) {
 let connected = false;
 return points.map(point => {
  const value = finiteValue(point[key]);
  if (value === null) { connected = false; return ""; }
  const command = connected ? "L" : "M";
  connected = true;
  return `${command}${x(point.date).toFixed(2)},${y(value).toFixed(2)}`;
 }).join(" ");
}
export function metricDomain(points: MarketPoint[], metric: RiskMetric): [number, number] {
 if (metric === "risk") return [0, 1];
 const values = points.flatMap(point => [finiteValue(point.msi), finiteValue(point.threshold)]).filter((v): v is number => v !== null);
 if (!values.length) return [-1, 1];
 const low = Math.min(...values), high = Math.max(...values), pad = Math.max((high - low) * .12, .1);
 return [low - pad, high + pad];
}
