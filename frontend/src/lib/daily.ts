import { durationTicks, formatAxisDuration, formatCount } from "./format";

/** Top of the failures band on the daily chart's shared 0..1 y scale. */
export const FAIL_TOP = 0.2;
/** Floor of the time-saved band; the space between the bands separates them. */
export const SAVED_BASE = 0.3;

/** The daily chart's two panels mapped onto one shared y scale. */
export interface DailyScale {
  /** Seconds at the top of the time-saved band, a round tick at or above the busiest day. */
  savedTop: number;
  /** Failures at the top of the failures band, at least 1. */
  maxFailures: number;
  /** Position of `seconds` saved, from `SAVED_BASE` up to 1. */
  savedY: (seconds: number) => number;
  /** Position of `count` failures, from 0 up to `FAIL_TOP`. */
  failY: (count: number) => number;
  /** Y axis ticks as positions on the shared scale, each labeled in its own panel's unit. */
  ticks: { value: number; label: string }[];
  /** Grid line positions: the time-saved ticks and the failures floor. */
  gridTicks: number[];
}

/** Return the shared y scale for daily time saved and failures. */
export function dailyScale(days: { saved: number; failures: number }[]): DailyScale {
  const savedTicks = durationTicks(Math.max(0, ...days.map((d) => d.saved)));
  const savedTop = Math.max(1, savedTicks.at(-1) ?? 0);
  const maxFailures = Math.max(1, ...days.map((d) => d.failures));
  const savedY = (seconds: number) => SAVED_BASE + (seconds / savedTop) * (1 - SAVED_BASE);
  const failY = (count: number) => (count / maxFailures) * FAIL_TOP;
  return {
    savedTop,
    maxFailures,
    savedY,
    failY,
    ticks: [
      { value: failY(0), label: formatCount(0) },
      { value: failY(maxFailures), label: formatCount(maxFailures) },
      ...savedTicks.map((t) => ({ value: savedY(t), label: formatAxisDuration(t) })),
    ],
    gridTicks: [failY(0), ...savedTicks.map(savedY)],
  };
}
