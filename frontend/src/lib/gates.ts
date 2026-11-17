/** Helpers for gate rows, the gate detail, and flaky trees. */

import type { EventRow, GateDetail, GateRow } from "./api";

/** Return a key unique per (repo, gate name); null is its own repo. */
export function gateKey(gate: { repo: string | null; name: string }): string {
  return JSON.stringify([gate.repo, gate.name]);
}

/** Return the row for one gate, if `rows` has it. */
export function findGate(
  rows: GateRow[] | undefined,
  gate: { repo: string | null; name: string },
): GateRow | undefined {
  return rows?.find((row) => row.repo === gate.repo && row.name === gate.name);
}

/** Return how many passes a trend has, their median duration, and the latest one. */
export function trendStats(trend: GateDetail["trend"]): {
  count: number;
  median: number | null;
  latest: number | null;
} {
  if (trend.length === 0) return { count: 0, median: null, latest: null };
  const sorted = trend.map((point) => point.duration).sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2;
  return { count: trend.length, median, latest: trend.at(-1)!.duration };
}

/** Count the failures and passes (cached or not) among runs on one tree. */
export function tally(runs: Pick<EventRow, "outcome">[]): { fails: number; passes: number } {
  let fails = 0;
  let passes = 0;
  for (const run of runs) {
    if (run.outcome === "fail") fails += 1;
    else if (run.outcome === "pass" || run.outcome === "pass_unrecorded") passes += 1;
  }
  return { fails, passes };
}
