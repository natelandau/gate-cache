/** One day of the summary's `daily` series. */
export interface DayBucket {
  day: string;
  saved: number;
  failures: number;
  runs: number;
  /** Seconds the command ran. */
  spent: number;
  skips: number;
  /** Runs that checked the cache: the skip rate's denominator. */
  ran: number;
  /** Seconds of gate-cache overhead plus waits for concurrent runs. */
  cost: number;
}

const formatters = new Map<string, Intl.DateTimeFormat>();

function dayFormatter(tz: string): Intl.DateTimeFormat {
  let formatter = formatters.get(tz);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
    formatters.set(tz, formatter);
  }
  return formatter;
}

/** Return the `YYYY-MM-DD` day that Unix timestamp `ts` falls on in IANA zone `tz`. */
export function dayKey(ts: number, tz: string): string {
  const parts = dayFormatter(tz).formatToParts(new Date(ts * 1000));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export function zeroBucket(day: string): DayBucket {
  return { day, saved: 0, failures: 0, runs: 0, spent: 0, skips: 0, ran: 0, cost: 0 };
}

/** Return the calendar day after `day`, both `YYYY-MM-DD`. */
function nextDay(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

/**
 * Return `daily` with an empty bucket for every missing day, in day order.
 *
 * The series covers the day of `from` through the day before the exclusive `to`. Without
 * `from` it starts at the first recorded day. Recorded days outside the bounds are kept.
 *
 * @param daily Buckets as the API returns them; may have gaps.
 * @param from Inclusive lower bound in Unix seconds, or undefined for all time.
 * @param to Exclusive upper bound in Unix seconds, usually now.
 * @param tz IANA zone the days were bucketed in.
 * @param empty Builds the bucket for a day without events.
 */
export function fillDays<T extends { day: string }>(
  daily: T[],
  from: number | undefined,
  to: number,
  tz: string,
  empty: (day: string) => T,
): T[] {
  const byDay = new Map(daily.map((bucket) => [bucket.day, bucket]));
  const recorded = [...byDay.keys()].sort();
  const first = from === undefined ? recorded[0] : dayKey(from, tz);
  if (first === undefined) return [];
  // The bound is exclusive, so the last covered instant is one second before it.
  const last = dayKey(to - 1, tz);
  const days = new Set(recorded);
  for (let day = first; day <= last; day = nextDay(day)) days.add(day);
  return [...days].sort().map((day) => byDay.get(day) ?? empty(day));
}
