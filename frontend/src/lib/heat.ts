import { formatCount, formatDuration } from "./format";

/** Which heatmap ramp a grid uses: runs (blue), time saved (green), or failures (red). */
export type HeatMetric = "runs" | "saved" | "fail";

export type HeatStep = 0 | 1 | 2 | 3 | 4 | 5;

/**
 * Return the ramp step for `value` on a fixed scale of the visible maximum.
 *
 * Step 0 means no activity, so any value above zero lands in step 1 or higher.
 */
export function heatStep(value: number, max: number): HeatStep {
  if (value <= 0 || max <= 0) return 0;
  return Math.min(5, Math.max(1, Math.ceil((value / max) * 5))) as HeatStep;
}

/** Return the CSS color for ramp `step` of `metric`. */
export function heatColor(metric: HeatMetric, step: number): string {
  return step <= 0 ? "var(--heat-empty)" : `var(--heat-${metric}-${step})`;
}

/** The value a heatmap cell shows for `metric`. */
export function heatValue(
  bucket: { runs: number; saved: number; failures: number },
  metric: HeatMetric,
): number {
  if (metric === "saved") return bucket.saved;
  if (metric === "fail") return bucket.failures;
  return bucket.runs;
}

/** The label for `metric`, matching the tabs that pick it. */
export const HEAT_LABELS: Record<HeatMetric, string> = {
  runs: "Runs",
  saved: "Time saved",
  fail: "Failures",
};

/** The metric tabs of a heatmap module, in display order. */
export const HEAT_OPTIONS: { value: HeatMetric; label: string }[] = (
  ["runs", "saved", "fail"] as const
).map((value) => ({ value, label: HEAT_LABELS[value] }));

/** Return the local name of `weekday` (0 is Sunday) in the browser's locale. */
export function weekdayName(weekday: number, style: "short" | "long"): string {
  // 1970-01-04 is a Sunday.
  return new Date(1970, 0, 4 + weekday).toLocaleString(undefined, { weekday: style });
}

/** Render a cell value for `metric`: a duration for time saved, a count otherwise. */
export function formatHeatValue(metric: HeatMetric, value: number): string {
  return metric === "saved" ? formatDuration(value) : formatCount(value);
}
