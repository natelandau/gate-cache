/** Helpers for gate rows, the gate detail, and flaky trees. */

import type { EventRow, GateDetail, GateRow } from "./api";
import { formatDuration } from "./format";
import type { MixPart } from "./rank";
import { OTHER_COLOR, SPENT_COLORS } from "./spent";

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

/** Return one bar per histogram bin, labeled with its time range, such as "2s\u20133s". */
export function histogramBars(
  h: NonNullable<GateDetail["histogram"]>,
): { from: number; to: number; count: number; label: string }[] {
  return h.counts.map((count, i) => {
    const from = h.edges[i]!;
    const to = h.edges[i + 1]!;
    return { from, to, count, label: `${formatDuration(from)}\u2013${formatDuration(to)}` };
  });
}

/** Return the gate's time per source as share parts, sized by whole seconds, with sources past the palette in Other. */
export function sourceParts(rows: GateDetail["by_source"]): MixPart[] {
  const parts: MixPart[] = rows.slice(0, SPENT_COLORS.length).map((row, i) => ({
    key: row.key,
    label: row.label,
    count: Math.round(row.time_spent),
    color: SPENT_COLORS[i]!,
    title: row.title ?? undefined,
  }));
  const rest = rows.slice(SPENT_COLORS.length);
  if (rest.length > 0) {
    parts.push({
      key: "other",
      label: "Other",
      count: Math.round(rest.reduce((sum, row) => sum + row.time_spent, 0)),
      color: OTHER_COLOR,
      title: rest.map((row) => row.label).join(", "),
    });
  }
  return parts;
}

/**
 * Whether a gate name is a command line, as gate-cache records a gate run without --name.
 * A name with whitespace is taken as one; the CLI documents names without spaces.
 */
export function isCommandLine(name: string): boolean {
  // The same ASCII whitespace that the archive's gate column checks, so a name never shows
  // as both a keyed gate and a command line.
  return /[ \t\n\v\f\r]/.test(name);
}
