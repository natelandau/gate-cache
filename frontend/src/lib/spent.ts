/** Series and stacked rows for the daily time spent chart. */

import { currentScope, getSpent, type Spent, type SpentDay, type SpentGate, type SpentStatus } from "./api";
import { fillDays } from "./fill";
import { nowSeconds } from "./state.svelte";

/** One distinct hue per ranked gate, in rank order. */
export const SPENT_COLORS = [
  "var(--chart-series-1)",
  "var(--chart-series-2)",
  "var(--chart-series-3)",
  "var(--chart-series-4)",
  "var(--chart-series-5)",
];
export const OTHER_COLOR = "var(--chart-neutral)";

/** Return the color of the gate at `rank` (0 first), or gray for ranks past the palette. */
export function seriesColor(rank: number): string {
  return SPENT_COLORS[rank] ?? OTHER_COLOR;
}

/** One stacked part of the chart: a top gate, or every other gate together. */
export interface SpentSeries {
  key: string;
  label: string;
  color: string;
  /** The gate, or null for Other. */
  gate: SpentGate | null;
}

/** One day's bar: its total and each series' slice of the stack, bottom first. */
export interface SpentRow {
  day: string;
  total: number;
  segments: { key: string; start: number; end: number }[];
}

/** Return the chart's series: the top gates in rank order, then Other when it has any time. */
export function spentSeries(body: Spent): SpentSeries[] {
  const series: SpentSeries[] = body.gates.slice(0, SPENT_COLORS.length).map((gate, index) => ({
    key: String(index),
    label: gate.label,
    color: seriesColor(index),
    gate,
  }));
  const shown = series.length;
  if (body.daily.some((day) => day.other > 0 || day.gates.slice(shown).some((v) => v > 0))) {
    series.push({ key: "other", label: "Other", color: OTHER_COLOR, gate: null });
  }
  return series;
}

/** Return one stacked row per day, with the largest gate at the bottom. */
export function spentRows(days: SpentDay[], series: SpentSeries[]): SpentRow[] {
  return days.map((d) => {
    let top = 0;
    // Gates without a series of their own count as Other.
    const dropped = d.gates.slice(series.filter((s) => s.gate).length).reduce((sum, v) => sum + v, 0);
    // Gate series come first, in the order of each day's `gates`.
    const segments = series.map((s, index) => {
      const seconds = s.gate ? (d.gates[index] ?? 0) : d.other + dropped;
      const start = top;
      top += seconds;
      return { key: s.key, start, end: top };
    });
    return { day: d.day, total: top, segments };
  });
}

/** Return a builder of zero days for `fillDays`, with one slot for each of `width` gates. */
export function emptySpentDay(width: number): (day: string) => SpentDay {
  return (day) => ({ day, gates: Array<number>(width).fill(0), other: 0 });
}

/** The time spent chart's data: its series and one stacked row per day of the range. */
export interface SpentView {
  series: SpentSeries[];
  rows: SpentRow[];
}

/**
 * Fetch time spent for the whole range of the global filters, never a picked span, so the
 * top gates and the days stay the same while days are picked.
 */
export async function loadSpent(signal: AbortSignal, status: SpentStatus): Promise<SpentView> {
  const now = nowSeconds();
  const scope = currentScope(now);
  const body = await getSpent(status, { signal, scope });
  const series = spentSeries(body);
  const days = fillDays(body.daily, scope.from, scope.to ?? now, scope.tz, emptySpentDay(body.gates.length));
  return { series, rows: spentRows(days, series) };
}

/** One series' share of the range, for the legend beside the chart. */
export interface SpentTotal {
  key: string;
  name: string;
  repo: string;
  color: string;
  gate: SpentGate | null;
  total: number;
}

/** Return each series' seconds over the range, in series order, and their sum. */
export function spentTotals(series: SpentSeries[], rows: SpentRow[]): { items: SpentTotal[]; total: number } {
  const items = series.map((s) => ({
    key: s.key,
    name: s.gate ? s.gate.name : s.label,
    repo: s.gate ? s.gate.repo_name : "",
    color: s.color,
    gate: s.gate,
    // The API totals each gate over the range; only Other is summed from the days.
    total: s.gate
      ? s.gate.total
      : rows.reduce((sum, row) => {
          const segment = row.segments.find((g) => g.key === s.key);
          return sum + (segment ? segment.end - segment.start : 0);
        }, 0),
  }));
  return { items, total: items.reduce((sum, i) => sum + i.total, 0) };
}
