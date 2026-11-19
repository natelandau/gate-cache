const MINUTE = 60;
export const HOUR = 3600;
export const DAY = 86400;

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

/**
 * Return axis ticks for counts from 0 up to at least `max`, on a step of 1, 2, or 5 times a
 * power of ten with at most `count` intervals. Always at least [0, 1], so an empty axis has a top.
 */
export function countTicks(max: number, count = 4): number[] {
  const target = Math.max(1, max);
  const magnitude = 10 ** Math.floor(Math.log10(target / count));
  const step = Math.max(1, [1, 2, 5, 10].map((m) => m * magnitude).find((s) => target / s <= count)!);
  const intervals = Math.ceil(target / step);
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

/** One number of a value that shows several, such as the "6 failed" of "21 ran, 6 failed". */
export interface ValuePart {
  /** The formatted number, such as "21". */
  value: string;
  /** A word after the number, set smaller and muted like a unit, such as "ran". */
  unit?: string;
  tone?: "danger";
}

/** Render a value as plain text, joining several parts with commas, such as "21 ran, 6 failed". */
export function valueText(value: string | ValuePart[]): string {
  if (typeof value === "string") return value;
  return value.map((p) => (p.unit ? `${p.value} ${p.unit}` : p.value)).join(", ");
}

/** Split a pause between runs into whole days from 48 hours up, and whole hours below. */
function idleUnits(seconds: number): { count: number; days: boolean } {
  return seconds >= 2 * DAY
    ? { count: Math.round(seconds / DAY), days: true }
    : { count: Math.max(1, Math.round(seconds / HOUR)), days: false };
}

/** Render a pause between runs for an axis, such as "9d" from 48 hours up and "36h" below. */
export function formatGap(seconds: number): string {
  const { count, days } = idleUnits(seconds);
  return `${count}${days ? "d" : "h"}`;
}

/** Render a pause between runs in words, such as "9 days" from 48 hours up and "36 hours" below. */
export function formatIdle(seconds: number): string {
  const { count, days } = idleUnits(seconds);
  return days ? plural(count, "day", "days") : plural(count, "hour", "hours");
}
