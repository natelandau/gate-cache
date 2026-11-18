import type { PreviousTotals, Summary } from "./api";
import type { Stat } from "./components/StatStrip.svelte";
import { formatCount, formatDuration } from "./format";

export type Delta = NonNullable<Stat["delta"]>;

export type DeltaKey =
  | "time_saved"
  | "net_saved"
  | "time_spent"
  | "runs"
  | "skip_rate"
  | "flaky_gates"
  | "failures";

type Kind = "percent" | "points" | "count";

/** How each stat measures change and which direction is better. */
const RULES: Record<DeltaKey, { kind: Kind; upIsGood: boolean; duration?: boolean }> = {
  time_saved: { kind: "percent", upIsGood: true, duration: true },
  // Net time saved can cross zero, where a percentage means nothing.
  net_saved: { kind: "count", upIsGood: true, duration: true },
  time_spent: { kind: "percent", upIsGood: false, duration: true },
  runs: { kind: "percent", upIsGood: true },
  skip_rate: { kind: "points", upIsGood: true },
  flaky_gates: { kind: "count", upIsGood: false },
  failures: { kind: "percent", upIsGood: false },
};

function delta(now: number, before: number, rule: (typeof RULES)[DeltaKey]): Delta {
  if (now === before) return { text: "No change", tone: "neutral" };
  const up = now > before;
  const tone = up === rule.upIsGood ? "good" : "bad";
  const arrow = up ? "▲" : "▼";
  let amount: string;
  if (rule.kind === "points") {
    const points = Math.round(Math.abs(now - before) * 100);
    amount = points === 0 ? "<1 pt" : `${formatCount(points)} ${points === 1 ? "pt" : "pts"}`;
  } else if (rule.kind === "percent" && before !== 0) {
    const percent = Math.round(Math.abs((now - before) / before) * 100);
    amount = percent === 0 ? "<1%" : `${formatCount(percent)}%`;
  } else {
    const size = Math.abs(now - before);
    amount = rule.duration ? formatDuration(size) : formatCount(size);
  }
  return { text: `${arrow} ${amount}`, tone };
}

/**
 * Return the change of each headline stat against the previous window. Skip rate changes in
 * percentage points, flaky gates and any stat with a zero previous value change by an absolute
 * amount, and the rest by a whole percentage. A change too small to round to 1 reads "<1". Skip
 * rate has no delta when either window has no rate. Net time saved changes by an absolute
 * duration, and has no delta when the previous window has no comparable net value.
 */
export function statDeltas(
  current: Summary,
  previous: PreviousTotals,
): Record<DeltaKey, Stat["delta"]> {
  const rate =
    current.skip_rate === null || previous.skip_rate === null
      ? undefined
      : delta(current.skip_rate, previous.skip_rate, RULES.skip_rate);
  const net =
    previous.net_saved === null
      ? undefined
      : delta(current.net_saved, previous.net_saved, RULES.net_saved);
  return {
    time_saved: delta(current.time_saved, previous.time_saved, RULES.time_saved),
    net_saved: net,
    time_spent: delta(current.time_spent, previous.time_spent, RULES.time_spent),
    runs: delta(current.runs, previous.runs, RULES.runs),
    skip_rate: rate,
    flaky_gates: delta(current.flaky_gates, previous.flaky_gates, RULES.flaky_gates),
    failures: delta(current.failures, previous.failures, RULES.failures),
  };
}

/**
 * Return the text that follows each delta, such as "vs prev 30d". A window under two days reads
 * in whole hours, at least one; a longer one in days rounded up, so a partial day still counts.
 */
export function deltaLabel(previous: PreviousTotals): string {
  const days = previous.days;
  if (days < 2) return `vs prev ${Math.max(1, Math.round(days * 24))}h`;
  return `vs prev ${Math.ceil(days)}d`;
}
