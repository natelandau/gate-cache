import { countTicks, formatCount } from "./format";


/** Top of the failures band on the daily chart's shared 0..1 y scale. */
export const FAIL_TOP = 0.2;
/** Floor of the runs band; the space between the bands separates them. */
export const RUNS_BASE = 0.3;

/** The daily chart's two panels mapped onto one shared y scale. */
export interface DailyScale {
  /** Runs at the top of the runs band, a round tick at or above the busiest day. */
  runsTop: number;
  /** Failures at the top of the failures band, at least 1. */
  maxFailures: number;
  /** Position of `count` runs, from `RUNS_BASE` up to 1. */
  runsY: (count: number) => number;
  /** Position of `count` failures, from 0 up to `FAIL_TOP`. */
  failY: (count: number) => number;
  /** Y axis ticks as positions on the shared scale, each labeled in its own panel's unit. */
  ticks: { value: number; label: string }[];
  /** Grid line positions: the runs ticks and the failures floor. */
  gridTicks: number[];
}

/** Return the shared y scale for daily runs and failures. */
export function dailyScale(days: { runs: number; failures: number }[]): DailyScale {
  const runsTicks = countTicks(Math.max(0, ...days.map((d) => d.runs)));
  const runsTop = runsTicks.at(-1)!;
  const maxFailures = Math.max(1, ...days.map((d) => d.failures));
  const runsY = (count: number) => RUNS_BASE + (count / runsTop) * (1 - RUNS_BASE);
  const failY = (count: number) => (count / maxFailures) * FAIL_TOP;
  return {
    runsTop,
    maxFailures,
    runsY,
    failY,
    ticks: [
      { value: failY(0), label: formatCount(0) },
      { value: failY(maxFailures), label: formatCount(maxFailures) },
      ...runsTicks.map((t) => ({ value: runsY(t), label: formatCount(t) })),
    ],
    gridTicks: [failY(0), ...runsTicks.map(runsY)],
  };
}

/**
 * Return the outer padding, in percent of the plot width, of a band scale with `count` bands
 * and d3's `padding`, which sets inner and outer padding alike. Columns of equal width inside
 * that inset line up with the bands, one step per day.
 */
export function bandInset(count: number, padding: number): number {
  return count === 0 ? 0 : ((padding / 2) / (count + padding)) * 100;
}

/**
 * Return the index of the band under `fraction` of the plot width (0 at the left edge, 1 at
 * the right), or null off the plot. The outer padding counts as its nearest band.
 */
export function bandIndexAt(fraction: number, count: number, padding: number): number | null {
  if (count === 0 || fraction < 0 || fraction > 1) return null;
  const inset = bandInset(count, padding) / 100;
  const index = Math.floor(((fraction - inset) / (1 - 2 * inset)) * count);
  return Math.min(count - 1, Math.max(0, index));
}
