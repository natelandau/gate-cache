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

/** Return the weekday of a `YYYY-MM-DD` day, 0 for Monday through 6 for Sunday. */
function mondayIndex(day: string): number {
  return (new Date(`${day}T00:00:00Z`).getUTCDay() + 6) % 7;
}

/**
 * Return `days` as Monday-first weeks, one array of seven per week, with null padding
 * before the first day and after the last.
 */
export function monthGrid(days: string[]): (string | null)[][] {
  if (days.length === 0) return [];
  const cells: (string | null)[] = [...Array<null>(mondayIndex(days[0]!)).fill(null), ...days];
  while (cells.length % 7 !== 0) cells.push(null);
  const weeks: (string | null)[][] = [];
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
