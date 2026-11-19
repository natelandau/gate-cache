/** Bars and drill-downs for the overview's Breakdown panel. */

import type { ActivityGroup, BreakdownRow } from "./api";
import type { Bar } from "./components/BarList.svelte";
import { dimension, type Dimension } from "./dimensions";
import { UNKNOWN_REPO, type Route } from "./router.svelte";
import type { SortState } from "./table";

export type Metric = "saved" | "spent" | "avg" | "median" | "runs" | "skip" | "fails" | "gates";

/** A sort on the Breakdown table: a numeric column, or the row name. */
export type BreakdownSort = SortState<Metric | "name">;

/** The Breakdown table's sort until the user picks a column: most run time first. */
export const DEFAULT_SORT: BreakdownSort = { key: "spent", direction: "desc" };

/** Return what the bars measure under `sort`: the sorted column, or run time for a name sort. */
export function barMetric(sort: BreakdownSort): Metric {
  return sort.key === "name" ? "spent" : sort.key;
}

function metricValue(row: BreakdownRow, by: Metric): number | null {
  switch (by) {
    case "saved":
      return row.time_saved;
    case "spent":
      return row.time_spent;
    case "avg":
      return row.avg_run;
    case "median":
      return row.median_run;
    case "runs":
      return row.runs;
    case "skip":
      return row.skip_rate;
    case "fails":
      return row.failures;
    case "gates":
      return row.gates;
  }
}

/**
 * Return one bar per row in `sort` order, ties by label; each bar's length is the sorted
 * column, or time spent when sorted by name. Rows of a dimension that covers every repo are
 * keyed by the repo filter value, and with a non-empty `selected`, repos outside it are
 * dimmed. Other dimensions already follow the repo filter, so nothing is dimmed.
 */
export function breakdownBars(
  rows: BreakdownRow[],
  sort: BreakdownSort,
  group: Dimension,
  selected: string[],
): Bar<BreakdownRow>[] {
  const by = barMetric(sort);
  const sign = sort.direction === "asc" ? 1 : -1;
  const chosen = new Set(selected);
  const allRepos = dimension(group).allRepos ?? false;
  return rows
    .map((row) => {
      const key = allRepos ? (row.repo ?? UNKNOWN_REPO) : row.key;
      const value = metricValue(row, by);
      return {
        key,
        label: row.label,
        title: row.title ?? undefined,
        value: value ?? 0,
        missing: value === null,
        dimmed: allRepos && chosen.size > 0 && !chosen.has(key),
        row,
      };
    })
    // Rows with no value for the sorted column go last in either direction, as in DataTable.
    .sort((a, b) => {
      if (sort.key === "name") return sign * a.label.localeCompare(b.label);
      if (a.missing !== b.missing) return a.missing ? 1 : -1;
      return sign * (a.value - b.value) || a.label.localeCompare(b.label);
    })
    .map(({ missing: _, ...bar }) => bar);
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
  return { kind: "activity", route: { page: "activity", group: rowGroup(group, row) } };
}

/** Return the Activity filter to the runs of one Breakdown row, with chip text such as "Branch: main". */
export function rowGroup(by: Dimension, row: Pick<BreakdownRow, "key" | "label">): ActivityGroup {
  return { by, key: row.key, label: `${dimension(by).label}: ${row.label}` };
}
