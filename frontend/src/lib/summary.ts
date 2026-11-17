import { currentScope, getSummary, type Summary } from "./api";
import type { Stat } from "./components/StatStrip.svelte";
import { statDeltas } from "./deltas";
import { type DayBucket, fillDays } from "./fill";
import { formatCount, formatDuration, formatPercent } from "./format";
import { nowSeconds } from "./state.svelte";

/** The summary with its daily series gap-filled across the selected range. */
export interface SummaryView {
  summary: Summary;
  days: DayBucket[];
}

/** Fetch the summary for the global filters and fill the days without events. */
export async function loadSummary(signal: AbortSignal): Promise<SummaryView> {
  const now = nowSeconds();
  const scope = currentScope(now);
  const summary = await getSummary({ signal, scope });
  return { summary, days: fillDays(summary.daily, scope.from, scope.to ?? now, scope.tz) };
}

function plural(count: number, one: string, many: string): string {
  return `${formatCount(count)} ${count === 1 ? one : many}`;
}

/**
 * Return the headline numbers of a summary for a stat strip. `flakyHref` links a non-zero flaky
 * gate count. Each stat carries its change against the previous window when the summary has one.
 */
export function summaryStats(s: Summary, options: { flakyHref?: string } = {}): Stat[] {
  const deltas = s.previous ? statDeltas(s, s.previous) : undefined;
  return [
    { label: "Time saved", value: formatDuration(s.time_saved), delta: deltas?.time_saved },
    {
      label: "Runs",
      value: formatCount(s.runs),
      hint: s.uncached ? `${formatCount(s.uncached)} uncached` : undefined,
      delta: deltas?.runs,
    },
    {
      label: "Skip rate",
      value: formatPercent(s.skip_rate),
      hint: plural(s.skips, "skip", "skips"),
      delta: deltas?.skip_rate,
    },
    {
      label: "Flaky gates",
      value: formatCount(s.flaky_gates),
      tone: s.flaky_gates ? "flaky" : "default",
      href: s.flaky_gates ? options.flakyHref : undefined,
      delta: deltas?.flaky_gates,
    },
    {
      label: "Failures",
      value: formatCount(s.failures),
      tone: s.failures ? "danger" : "default",
      delta: deltas?.failures,
    },
  ];
}

/** Return the footnote for skips that add nothing to time saved, or undefined when none. */
export function summaryNote(s: Summary): string | undefined {
  const unknown = s.unknown_saved_skips;
  if (!unknown) return undefined;
  return `${plural(unknown, "skip", "skips")} had no recorded duration, so ${unknown === 1 ? "it adds" : "they add"} nothing to time saved.`;
}
