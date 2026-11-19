import { TERMS } from "./terms";
import { currentScope, getSummary, type Summary } from "./api";
import type { Stat } from "./components/StatStrip.svelte";
import { statDeltas } from "./deltas";
import { type DayBucket, fillDays, zeroBucket } from "./fill";
import {
  formatCount,
  formatDuration,
  formatPercent,
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

interface StatContext {
  s: Summary;
  options: SummaryStatOptions;
  deltas: ReturnType<typeof statDeltas> | undefined;
  spark: (...series: SparkLine[]) => Stat["spark"];
}

/** A sparkline's CSS color and the value it plots for each day. */
type SparkLine = [color: string, value: (d: DayBucket) => number | null];

interface SummaryStatOptions {
  runsHref?: string;
  flakyHref?: string;
  failuresHref?: string;
  spotChecksHref?: string;
}

const STAT_BUILDERS: ((c: StatContext) => Stat)[] = [
  (c) => ({
    label: TERMS.calls.label,
    value: formatCount(c.s.runs),
    title: TERMS.calls.about,
    // Every call counts, so the hint splits the calls that ran from the ones the cache skipped.
    hint: c.s.runs ? `${formatCount(c.s.runs - c.s.skips)} ran · ${formatCount(c.s.skips)} skipped` : undefined,
    href: c.s.runs ? c.options.runsHref : undefined,
    delta: c.deltas?.runs,
    spark: c.spark(["var(--chart-runs)", (d) => d.runs]),
  }),
  (c) => ({
    label: TERMS.ran.label,
    value: formatDuration(c.s.time_spent),
    hint: c.s.fail_time > 0 ? `${formatDuration(c.s.fail_time)} on failures` : undefined,
    title: TERMS.ran.about,
    delta: c.deltas?.time_spent,
    spark: c.spark(["var(--chart-runs)", (d) => d.spent]),
  }),
  (c) => ({
    label: TERMS.saved.label,
    value: formatDuration(c.s.time_saved),
    title: TERMS.saved.about,
    delta: c.deltas?.time_saved,
    spark: c.spark(["var(--chart-saved)", (d) => d.saved]),
  }),
  (c) => ({
    label: TERMS.failures.label,
    value: formatCount(c.s.failures),
    title:
      "Calls whose command failed, plus calls that reported the failure of a concurrent run " +
      "they waited for instead of running again.",
    tone: c.s.failures ? "danger" : "default",
    href: c.s.failures ? c.options.failuresHref : undefined,
    delta: c.deltas?.failures,
    spark: c.spark(["var(--chart-failures)", (d) => d.failures]),
  }),
  (c) => ({
    label: TERMS.flaky.label,
    value: formatCount(c.s.flaky_gates),
    title: "Gates that both failed and passed on the same content, so the result changed with no code change.",
    tone: c.s.flaky_gates ? "flaky" : "default",
    href: c.s.flaky_gates ? c.options.flakyHref : undefined,
    delta: c.deltas?.flaky_gates,
  }),
  (c) => ({
    label: TERMS.spotChecks.label,
    value: [
      { value: formatCount(c.s.spot_checks), unit: TERMS.spotChecks.ran },
      {
        value: formatCount(c.s.spot_check_failures),
        unit: TERMS.spotChecks.failed,
        tone: c.s.spot_check_failures ? "danger" : undefined,
      },
    ],
    title: TERMS.spotChecks.aboutCard,
    href: c.s.spot_checks ? c.options.spotChecksHref : undefined,
    delta: c.deltas?.spot_check_failures,
    spark: c.spark(["var(--chart-runs)", (d) => d.spot_checks], ["var(--chart-failures)", (d) => d.spot_check_failures]),
  }),
  (c) => ({
    label: TERMS.skipRate.label,
    value: formatPercent(c.s.skip_rate),
    title: TERMS.skipRate.about,
    hint: `${formatCount(c.s.skips)} of ${formatCount(c.s.runs - c.s.uncached)} skipped`,
    delta: c.deltas?.skip_rate,
    spark: c.spark(["var(--chart-runs)", (d) => (d.ran ? d.skips / d.ran : null)]),
  }),
];

/** How many stats `summaryStats` returns, for skeleton cards that stand in while it loads. */
export const SUMMARY_STAT_COUNT = STAT_BUILDERS.length;

/**
 * Return the headline numbers of a summary for a stat strip. The hrefs link the run, flaky
 * gate, failure, and spot check counts when they are not zero. Each stat carries its change
 * against the previous window when the summary has one, and a sparkline of `daily` when given.
 */
export function summaryStats(
  s: Summary,
  options: SummaryStatOptions = {},
  daily?: DayBucket[],
): Stat[] {
  const deltas = s.previous ? statDeltas(s, s.previous) : undefined;
  const spark = (...series: SparkLine[]) =>
    daily && daily.length > 0 ? series.map(([color, value]) => ({ values: daily.map(value), color })) : undefined;
  return STAT_BUILDERS.map((build) => build({ s, options, deltas, spark }));
}

/** Return the footnote for skips that add nothing to time saved, or undefined when there are none. */
export function summaryNote(s: Summary): string | undefined {
  const unknown = s.unknown_saved_skips;
  if (!unknown) return undefined;
  return `${plural(unknown, "skipped call", "skipped calls")} had no recorded duration, so ${unknown === 1 ? "it adds" : "they add"} nothing to time saved by cache.`;
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
