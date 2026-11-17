/** Rows for the homepage's Repos bar list. */

import type { RepoRow } from "./api";
import { UNKNOWN_REPO } from "./router.svelte";

export type RepoMetric = "saved" | "runs" | "skip" | "fails";

export interface RepoBar {
  /** The repo filter value: the git common directory, or `-` for the unknown repo. */
  key: string;
  label: string;
  value: number;
  /** True when a repo filter is active and leaves this repo out. */
  dimmed: boolean;
  row: RepoRow;
}

function metricValue(row: RepoRow, by: RepoMetric): number {
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
 * Return one bar per repo, largest `by` first and ties by name. With a non-empty `selected`,
 * repos outside it are dimmed.
 */
export function repoBars(rows: RepoRow[], by: RepoMetric, selected: string[]): RepoBar[] {
  const chosen = new Set(selected);
  return rows
    .map((row) => {
      const key = row.repo ?? UNKNOWN_REPO;
      return {
        key,
        label: row.repo_name,
        value: metricValue(row, by),
        dimmed: chosen.size > 0 && !chosen.has(key),
        row,
      };
    })
    .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));
}
