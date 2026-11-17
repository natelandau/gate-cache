import { currentScope, getSummary, type RequestOptions, type Summary } from "./api";
import type { Stat } from "./components/StatStrip.svelte";
import { type DayBucket, fillDays } from "./fill";
import { formatCount, formatDuration, formatPercent } from "./format";
import { nowSeconds } from "./state.svelte";

/** The summary with its daily series gap-filled across the selected range. */
export interface SummaryView {
  summary: Summary;
  days: DayBucket[];
}

/**
 * Fetch the summary for the global filters, or for `repo` over the global range, and fill the
 * days without events.
 */
export async function loadSummary(
  signal: AbortSignal,
  repo?: RequestOptions["repo"],
): Promise<SummaryView> {
  const now = nowSeconds();
  const scope = currentScope(now);
  const summary = await getSummary({ signal, scope, repo });
  return { summary, days: fillDays(summary.daily, scope.from, scope.to ?? now, scope.tz) };
}

function plural(count: number, one: string, many: string): string {
  return `${formatCount(count)} ${count === 1 ? one : many}`;
}

/**
 * Return the headline numbers of a summary for a stat strip. `flakyHref` links a non-zero flaky
 * gate count, for pages whose scope matches the Flaky page's.
 */
export function summaryStats(s: Summary, options: { flakyHref?: string } = {}): Stat[] {
  return [
    { label: "Time saved", value: formatDuration(s.time_saved) },
    {
      label: "Runs",
      value: formatCount(s.runs),
      hint: s.uncached ? `${formatCount(s.uncached)} uncached` : undefined,
    },
    {
      label: "Skip rate",
      value: formatPercent(s.skip_rate),
      hint: plural(s.skips, "skip", "skips"),
    },
    {
      label: "Flaky gates",
      value: formatCount(s.flaky_gates),
      tone: s.flaky_gates ? "flaky" : "default",
      href: s.flaky_gates ? options.flakyHref : undefined,
    },
    {
      label: "Failures",
      value: formatCount(s.failures),
      tone: s.failures ? "danger" : "default",
    },
  ];
}

/** Return the footnote for skips that add nothing to time saved, or undefined when none. */
export function summaryNote(s: Summary): string | undefined {
  const unknown = s.unknown_saved_skips;
  if (!unknown) return undefined;
  return `${plural(unknown, "skip", "skips")} had no recorded duration, so ${unknown === 1 ? "it adds" : "they add"} nothing to time saved.`;
}
