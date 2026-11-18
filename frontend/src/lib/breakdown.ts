/** Bars and drill-downs for the overview's Breakdown panel. */

import type { BreakdownRow } from "./api";
import type { Bar } from "./components/BarList.svelte";
import { dimension, type Dimension } from "./dimensions";
import { UNKNOWN_REPO, type Route } from "./router.svelte";

export type Metric = "saved" | "runs" | "skip" | "fails";

function metricValue(row: BreakdownRow, by: Metric): number {
  switch (by) {
    case "saved":
      return row.time_saved;
    case "runs":
      return row.runs;
    case "skip":
      return row.skip_rate ?? 0;
    case "fails":
      return row.failures;
  }
}

/**
 * Return one bar per row, largest `by` first and ties by label. Rows of a dimension that covers
 * every repo are keyed by the repo filter value, and with a non-empty `selected`, repos outside
 * it are dimmed. Other dimensions already follow the repo filter, so nothing is dimmed.
 */
export function breakdownBars(
  rows: BreakdownRow[],
  by: Metric,
  group: Dimension,
  selected: string[],
): Bar<BreakdownRow>[] {
  const chosen = new Set(selected);
  const allRepos = dimension(group).allRepos ?? false;
  return rows
    .map((row) => {
      const key = allRepos ? (row.repo ?? UNKNOWN_REPO) : row.key;
      return {
        key,
        label: row.label,
        title: row.title ?? undefined,
        value: metricValue(row, by),
        dimmed: allRepos && chosen.size > 0 && !chosen.has(key),
        row,
      };
    })
    .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));
}

/** What clicking a Breakdown row does. */
export type DrillDown =
  | { kind: "repo"; repo: string }
  | { kind: "gate"; repo: string | null; name: string }
  | { kind: "activity"; route: Route };

/**
 * Return the drill-down for a row: a Repo row filters the dashboard to that repo, a Gate row
 * opens the gate's panel, and any other row opens Activity filtered to the row's runs.
 */
export function drillDown(group: Dimension, row: BreakdownRow): DrillDown {
  if (group === "repo") return { kind: "repo", repo: row.repo ?? UNKNOWN_REPO };
  if (group === "gate" && row.name !== null) return { kind: "gate", repo: row.repo, name: row.name };
  const label = `${dimension(group).label}: ${row.label}`;
  return { kind: "activity", route: { page: "activity", group: { by: group, key: row.key, label } } };
}
