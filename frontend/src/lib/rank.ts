/** Rankings and shares for the homepage modules. */

import type { FlakyGate, GateRow } from "./api";

/** What Top gates ranks by: time saved, runs, failures, or median passing run time. */
export type GateRank = "saved" | "runs" | "fails" | "slow";

const RANK_VALUE: Record<GateRank, (row: GateRow) => number | null> = {
  saved: (row) => row.time_saved,
  runs: (row) => row.runs,
  fails: (row) => row.failures,
  slow: (row) => row.median_run,
};

/** Return the value `by` ranks `row` on; null when the gate has no median run time. */
export function rankValue(row: GateRow, by: GateRank): number | null {
  return RANK_VALUE[by](row);
}

type Named = { name: string; repo_name: string };

function byName(a: Named, b: Named): number {
  return a.name.localeCompare(b.name) || a.repo_name.localeCompare(b.repo_name);
}

/**
 * Return the top `limit` gates by `by`, highest first, ties by name. Gates without a median
 * run time drop out of `slow`.
 */
export function rankGates(rows: GateRow[], by: GateRank, limit = 8): GateRow[] {
  return rows
    .filter((row) => rankValue(row, by) !== null)
    .sort((a, b) => rankValue(b, by)! - rankValue(a, by)! || byName(a, b))
    .slice(0, limit);
}

/** Return the `limit` gates with the most flaky trees, ties by name. */
export function topFlaky(gates: FlakyGate[], limit = 5): FlakyGate[] {
  return [...gates].sort((a, b) => b.tree_count - a.tree_count || byName(a, b)).slice(0, limit);
}

/** One part of a whole, for a stacked share bar. */
export interface MixPart {
  key: string;
  label: string;
  count: number;
  /** A chart color token, such as `var(--chart-skip)`. */
  color: string;
  /** Optional longer description, shown as a tooltip on the legend row. */
  title?: string;
  /** Optional link to the runs this part counts; a part with no count gets no link. */
  href?: string;
}

export interface PartShare<T> {
  part: T;
  count: number;
  /** 0..1 of the total; 0 when the total is 0. */
  share: number;
  /** Whole percent, or "<1%" for a nonzero count that rounds to zero. */
  percent: string;
}

/** Return each item, in order, with its count and share of the sum of all counts. */
export function partShares<T>(items: T[], count: (item: T) => number): PartShare<T>[] {
  const total = items.reduce((sum, item) => sum + count(item), 0);
  return items.map((part) => {
    const n = count(part);
    const share = total > 0 ? n / total : 0;
    const whole = Math.round(share * 100);
    return { part, count: n, share, percent: n > 0 && whole === 0 ? "<1%" : `${whole}%` };
  });
}
