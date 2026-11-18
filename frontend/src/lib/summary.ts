import { currentScope, getSummary, type Summary } from "./api";
import type { Stat } from "./components/StatStrip.svelte";
import { statDeltas } from "./deltas";
import { type DayBucket, fillDays } from "./fill";
import {
  formatCount,
  formatDuration,
  formatPercent,
  formatSignedDuration,
  isNegativeDuration,
  plural,
} from "./format";
import { clampScope, type DaySpan } from "./selection";
import { nowSeconds } from "./state.svelte";

/** The summary with its daily series gap-filled across the selected range. */
export interface SummaryView {
  summary: Summary;
  days: DayBucket[];
}

/** Fetch the summary for the global filters, narrowed to `span` when given, and fill the days without events. */
export async function loadSummary(signal: AbortSignal, span?: DaySpan): Promise<SummaryView> {
  const now = nowSeconds();
  const scope = clampScope(currentScope(now), span);
  const summary = await getSummary({ signal, scope });
  return { summary, days: fillDays(summary.daily, scope.from, scope.to ?? now, scope.tz) };
}

/**
 * Return the headline numbers of a summary for a stat strip. The hrefs link the run, flaky
 * gate, and failure counts when they are not zero. Each stat carries its change against the
 * previous window when the summary has one.
 */
export function summaryStats(
  s: Summary,
  options: { runsHref?: string; flakyHref?: string; failuresHref?: string } = {},
): Stat[] {
  const deltas = s.previous ? statDeltas(s, s.previous) : undefined;
  return [
    { label: "Time saved", value: formatDuration(s.time_saved), delta: deltas?.time_saved },
    {
      label: "Net saved",
      value: formatSignedDuration(s.net_saved),
      hint: `minus ${formatDuration(s.overhead + s.waited)} overhead and waits`,
      title:
        "Time saved minus the time gate-cache spent deciding whether to skip, and minus the " +
        "time runs waited for a concurrent run of the same gate. Negative means the cache cost " +
        "more than it saved.",
      tone: isNegativeDuration(s.net_saved) ? "danger" : "default",
      delta: deltas?.net_saved,
    },
    {
      label: "Runs",
      value: formatCount(s.runs),
      hint: s.uncached ? `${formatCount(s.uncached)} uncached` : undefined,
      href: s.runs ? options.runsHref : undefined,
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
      href: s.failures ? options.failuresHref : undefined,
      delta: deltas?.failures,
    },
  ];
}

/**
 * Return the footnote for numbers the range cannot fully back: skips that add nothing to time
 * saved, and runs whose cost net saved leaves out. Undefined when the range has neither.
 */
export function summaryNote(s: Summary): string | undefined {
  const notes: string[] = [];
  const unknown = s.unknown_saved_skips;
  if (unknown) {
    notes.push(
      `${plural(unknown, "skip", "skips")} had no recorded duration, so ${unknown === 1 ? "it adds" : "they add"} nothing to time saved.`,
    );
  }
  const costless = s.cost_unknown_runs;
  if (costless) {
    notes.push(
      `${plural(costless, "run", "runs")} came from an older gate-cache that did not record overhead or wait time, so net saved leaves out ${costless === 1 ? "its" : "their"} cost.`,
    );
  }
  return notes.length ? notes.join(" ") : undefined;
}
