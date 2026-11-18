/** Layout and summary facts for the activity calendar. */

import type { DayBucket } from "./fill";

/** Ranges up to this many days fit as month-style rows of weeks. */
const MONTH_MAX_DAYS = 42;

/**
 * Return how to lay out the calendar: week rows like a wall calendar for ranges up to six
 * weeks, where cells can be large, or week columns for longer ranges.
 */
export function calendarLayout(days: string[]): "month" | "weeks" {
  return days.length <= MONTH_MAX_DAYS ? "month" : "weeks";
}

/**
 * Split `items`, one per day in order, into weeks of seven, with `lead` blank cells before the
 * first day and blanks after the last to fill its week.
 */
export function chunkWeeks<T>(items: T[], lead: number): (T | null)[][] {
  if (items.length === 0) return [];
  const cells: (T | null)[] = [...Array<null>(lead).fill(null), ...items];
  while (cells.length % 7 !== 0) cells.push(null);
  const weeks: (T | null)[][] = [];
  for (let start = 0; start < cells.length; start += 7) weeks.push(cells.slice(start, start + 7));
  return weeks;
}

/** Return the busiest day, the count of days with runs, and the mean runs on those days. */
export function calendarFacts(buckets: DayBucket[]): {
  busiest: DayBucket | null;
  activeDays: number;
  totalDays: number;
  runsPerActiveDay: number | null;
} {
  const active = buckets.filter((b) => b.runs > 0);
  const busiest = active.reduce<DayBucket | null>((best, b) => (best && best.runs >= b.runs ? best : b), null);
  const runs = active.reduce((sum, b) => sum + b.runs, 0);
  return {
    busiest,
    activeDays: active.length,
    totalDays: buckets.length,
    runsPerActiveDay: active.length ? runs / active.length : null,
  };
}
