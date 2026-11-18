import { currentScope, getSummary, type Summary } from "./api";
import type { Stat } from "./components/StatStrip.svelte";
import { statDeltas } from "./deltas";
import { type DayBucket, fillDays, zeroBucket } from "./fill";
import {
  formatCount,
  formatDuration,
  formatPercent,
  formatSignedDuration,
  isNegativeDuration,
  plural,
} from "./format";
import { clampScope, selectedRange, spanOf, type DaySpan } from "./selection";
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
  return { summary, days: fillDays(summary.daily, scope.from, scope.to ?? now, scope.tz, zeroBucket) };
}

/**
 * Return the headline numbers of a summary for a stat strip, the gates' own numbers first and
 * what the cache saved last. The hrefs link the run, flaky
 * gate, and failure counts when they are not zero. Each stat carries its change against the
 * previous window when the summary has one, and a sparkline of `daily` when given.
 */
export function summaryStats(
  s: Summary,
  options: {
    runsHref?: string;
    flakyHref?: string;
    failuresHref?: string;
    /** Runs with unknown cost in the range `daily` covers, when wider than the summary's. */
    costUnknownRuns?: number;
  } = {},
  daily?: DayBucket[],
): Stat[] {
  const costUnknown = options.costUnknownRuns ?? s.cost_unknown_runs;
  const deltas = s.previous ? statDeltas(s, s.previous) : undefined;
  const spark = (color: string, value: (d: DayBucket) => number | null) =>
    daily && daily.length > 0 ? { values: daily.map(value), color } : undefined;
  return [
    {
      label: "Gate calls",
      value: formatCount(s.runs),
      title:
        "Every time a gate was called through gate-cache, whether its command ran or the cache " +
        "skipped it.",
      // Every call counts, so the hint splits the calls that ran from the ones the cache skipped.
      hint: s.runs ? `${formatCount(s.runs - s.skips)} ran · ${formatCount(s.skips)} skipped` : undefined,
      href: s.runs ? options.runsHref : undefined,
      delta: deltas?.runs,
      spark: spark("var(--chart-runs)", (d) => d.runs),
    },
    {
      label: "Time gates ran",
      value: formatDuration(s.time_spent),
      hint: s.fail_time > 0 ? `${formatDuration(s.fail_time)} on failures` : undefined,
      title:
        "Total time of the calls that ran, failed runs included. Skipped calls take no time, " +
        "and gate-cache overhead and waits are not counted.",
      delta: deltas?.time_spent,
      spark: spark("var(--chart-runs)", (d) => d.spent),
    },
    {
      label: "Gate failures",
      value: formatCount(s.failures),
      title:
        "Calls whose command failed, plus calls that reported the failure of a concurrent run " +
        "they waited for instead of running again.",
      tone: s.failures ? "danger" : "default",
      href: s.failures ? options.failuresHref : undefined,
      delta: deltas?.failures,
      spark: spark("var(--chart-failures)", (d) => d.failures),
    },
    {
      label: "Flaky gates",
      value: formatCount(s.flaky_gates),
      title: "Gates that both failed and passed on the same content, so the result changed with no code change.",
      tone: s.flaky_gates ? "flaky" : "default",
      href: s.flaky_gates ? options.flakyHref : undefined,
      delta: deltas?.flaky_gates,
    },
    {
      label: "Cache skip rate",
      value: formatPercent(s.skip_rate),
      title:
        "The share of calls that checked the cache and were skipped because the same gate " +
        "already passed on the same content. Calls with caching off are left out.",
      hint: `${formatCount(s.skips)} of ${formatCount(s.runs - s.uncached)} skipped`,
      delta: deltas?.skip_rate,
      spark: spark("var(--chart-runs)", (d) => (d.ran ? d.skips / d.ran : null)),
    },
    {
      label: "Time saved by cache",
      value: formatDuration(s.time_saved),
      title:
        "Run time that skipped calls did not spend, taken from the earlier passing run that let " +
        "each one skip.",
      delta: deltas?.time_saved,
      spark: spark("var(--chart-saved)", (d) => d.saved),
    },
    {
      label: "Net saved by cache",
      value: formatSignedDuration(s.net_saved),
      hint: `after ${formatDuration(s.overhead + s.waited)} of overhead`,
      title:
        "Time saved minus the time gate-cache spent deciding whether to skip, and minus the " +
        "time runs waited for a concurrent run of the same gate. Negative means the cache cost " +
        "more than it saved.",
      tone: isNegativeDuration(s.net_saved) ? "danger" : "default",
      delta: deltas?.net_saved,
      // Days with runs that recorded no cost would overstate net saved, as the delta would.
      spark: costUnknown > 0 ? undefined : spark("var(--chart-saved)", (d) => d.saved - d.cost),
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
      `${plural(unknown, "skipped call", "skipped calls")} had no recorded duration, so ${unknown === 1 ? "it adds" : "they add"} nothing to time saved by cache.`,
    );
  }
  const costless = s.cost_unknown_runs;
  if (costless) {
    notes.push(
      `${plural(costless, "call", "calls")} came from an older gate-cache that did not record overhead or wait time, so net saved by cache leaves out ${costless === 1 ? "its" : "their"} cost.`,
    );
  }
  return notes.length ? notes.join(" ") : undefined;
}

/**
 * Return the first and last index in `days` of the days a scoped summary covers, or undefined
 * until the scoped summary loads. Reading the loaded days, not the requested span, keeps a
 * sparkline's highlight in step with the values beside it.
 */
export function pickedRange(days: DayBucket[], scoped: DayBucket[] | undefined): [number, number] | undefined {
  const first = scoped?.[0]?.day;
  const last = scoped?.[scoped.length - 1]?.day;
  return first && last ? (selectedRange(days, spanOf(first, last)) ?? undefined) : undefined;
}
