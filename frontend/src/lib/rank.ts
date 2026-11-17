/** Rankings and shares for the homepage modules. */

import type { FlakyGate, GateRow, Outcome } from "./api";
import { OUTCOMES } from "./events";

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

export interface OutcomeShare {
  outcome: Outcome;
  count: number;
  /** 0..1 of all runs; 0 when nothing ran. */
  share: number;
  /** Whole percent, or "<1%" for a nonzero count that rounds to zero. */
  percent: string;
}

/** Return each outcome, in `OUTCOMES` order, with its count and share of all runs. */
export function outcomeShares(counts: Record<Outcome, number>): OutcomeShare[] {
  const outcomes = Object.keys(OUTCOMES) as Outcome[];
  const total = outcomes.reduce((sum, outcome) => sum + counts[outcome], 0);
  return outcomes.map((outcome) => {
    const count = counts[outcome];
    const share = total > 0 ? count / total : 0;
    const whole = Math.round(share * 100);
    return { outcome, count, share, percent: count > 0 && whole === 0 ? "<1%" : `${whole}%` };
  });
}
