const MINUTE = 60;
const HOUR = 3600;
const DAY = 86400;

/**
 * Render a duration in seconds the way the CLI does: `<1s`, `42s`, `1m 34s`, `1h 2m`.
 * Returns `n/a` for null.
 */
export function formatDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "n/a";
  if (seconds < 1) return "<1s";
  // Mirror the CLI's int(seconds + 0.5) so both print the same text for the same value.
  const total = Math.floor(seconds + 0.5);
  if (total < MINUTE) return `${total}s`;
  if (total < HOUR) return `${Math.floor(total / MINUTE)}m ${total % MINUTE}s`;
  const minutes = Math.floor((total + MINUTE / 2) / MINUTE);
  return `${Math.floor(minutes / MINUTE)}h ${minutes % MINUTE}m`;
}

/** Return whether a duration reads as at least one whole second below zero. */
export function isNegativeDuration(seconds: number): boolean {
  // formatDuration shows anything under a second as "<1s", which carries no sign.
  return seconds <= -1;
}

/** Render a duration that can be negative, with a leading minus sign (U+2212) when it is. */
export function formatSignedDuration(seconds: number): string {
  return isNegativeDuration(seconds) ? `\u2212${formatDuration(-seconds)}` : formatDuration(seconds);
}

/** Render an axis tick duration: ticks fall on whole units, so `10m 0s` reads as `10m`. */
export function formatAxisDuration(seconds: number): string {
  return seconds === 0 ? "0" : formatDuration(seconds).replace(/ 0[sm]$/, "");
}

/** Render a 0..1 rate as a whole percent, or `n/a` for null. */
export function formatPercent(rate: number | null): string {
  if (rate === null || !Number.isFinite(rate)) return "n/a";
  return `${Math.round(rate * 100)}%`;
}

/** Render how long ago `ts` was, relative to `now`, both in Unix seconds. */
export function formatRelative(ts: number, now: number): string {
  const elapsed = Math.max(0, Math.floor(now - ts));
  if (elapsed < MINUTE) return `${elapsed}s ago`;
  if (elapsed < HOUR) return `${Math.floor(elapsed / MINUTE)}m ago`;
  if (elapsed < DAY) return `${Math.floor(elapsed / HOUR)}h ago`;
  return `${Math.floor(elapsed / DAY)}d ago`;
}

const shortDayFormat = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});
const longDayFormat = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

/**
 * Render a `YYYY-MM-DD` day as month and day, such as "Nov 10". Day keys are calendar dates,
 * so both day formatters use UTC to avoid shifting by the local offset.
 */
export function formatShortDay(day: string): string {
  return shortDayFormat.format(new Date(`${day}T00:00:00Z`));
}

/** Render a `YYYY-MM-DD` day with weekday and year, such as "Tue, Nov 10, 2026". */
export function formatLongDay(day: string): string {
  return longDayFormat.format(new Date(`${day}T00:00:00Z`));
}

const countFormat = new Intl.NumberFormat("en-US");

/** Render an integer count with thousands separators. */
export function formatCount(value: number): string {
  return countFormat.format(value);
}

/** Render a count with its noun, such as "1 skip" or "1,204 skips". */
export function plural(count: number, one: string, many: string): string {
  return `${formatCount(count)} ${count === 1 ? one : many}`;
}

const timestampFormat = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "medium",
});

/** Render a Unix timestamp as a local date and time, for titles and detail views. */
export function formatTimestamp(ts: number): string {
  return timestampFormat.format(new Date(ts * 1000));
}

const DURATION_STEPS = [
  1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400,
];

/**
 * Return axis ticks for durations from 0 up to at least `max` seconds, on a readable step
 * (seconds, minutes, or hours) with at most `count` intervals.
 */
export function durationTicks(max: number, count = 3): number[] {
  if (!(max > 0)) return [0];
  const step =
    DURATION_STEPS.find((candidate) => Math.ceil(max / candidate) <= count) ??
    Math.ceil(max / count / 86400) * 86400;
  const intervals = Math.ceil(max / step);
  return Array.from({ length: intervals + 1 }, (_, index) => index * step);
}

const BYTE_UNITS = ["B", "KiB", "MiB", "GiB", "TiB"];

/** Render a byte count in binary units, such as `512 B`, `1.5 KiB`, `50.0 MiB`. Returns `n/a` for null. */
export function formatBytes(bytes: number | null): string {
  if (bytes === null || !Number.isFinite(bytes)) return "n/a";
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return unit === 0 ? `${Math.round(value)} B` : `${value.toFixed(1)} ${BYTE_UNITS[unit]}`;
}

/** Render a ratio with one decimal and a times sign, such as `3.4×`. Returns `n/a` for null. */
export function formatRatio(ratio: number | null): string {
  if (ratio === null || !Number.isFinite(ratio)) return "n/a";
  return `${ratio.toFixed(1)}×`;
}

/**
 * Split a formatted value into digits and units, so units can be set smaller: "6h 38m" gives
 * 6, h, space, 38, m. A leading sign stays with its number, and a value with no unit letters
 * comes back whole.
 */
export function valueParts(value: string): { text: string; unit: boolean }[] {
  if (!/\d/.test(value)) return [{ text: value, unit: false }];
  const parts: { text: string; unit: boolean }[] = [];
  for (const match of value.matchAll(/([−+-]?[\d.,]+)|([a-zA-Z%]+)|(\s+)|(.)/g)) {
    const [text, digits, unit] = match;
    parts.push({ text, unit: !digits && !!unit });
  }
  return parts;
}
