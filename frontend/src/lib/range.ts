/**
 * The date range model: rolling presets, calendar periods, and custom dates. Calendar periods
 * and custom dates follow the browser's local time, and weeks start on Sunday.
 */

export type Preset = "24h" | "7d" | "30d" | "90d" | "1y" | "all";

/** The rolling presets in display order. */
export const PRESETS: readonly { value: Preset; label: string; long: string }[] = [
  { value: "24h", label: "24h", long: "Last 24 hours" },
  { value: "7d", label: "7d", long: "Last 7 days" },
  { value: "30d", label: "30d", long: "Last 30 days" },
  { value: "90d", label: "90d", long: "Last 90 days" },
  { value: "1y", label: "1y", long: "Last 12 months" },
  { value: "all", label: "All", long: "All time" },
];

export type Period =
  | "today"
  | "yesterday"
  | "this_week"
  | "last_week"
  | "this_month"
  | "last_month"
  | "this_year"
  | "last_year";

/** The calendar periods in display order. */
export const PERIODS: readonly { value: Period; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "this_week", label: "This week" },
  { value: "last_week", label: "Last week" },
  { value: "this_month", label: "This month" },
  { value: "last_month", label: "Last month" },
  { value: "this_year", label: "This year" },
  { value: "last_year", label: "Last year" },
];

/** A date range. Custom dates are `YYYY-MM-DD` in local time, and `end` is inclusive. */
export type RangeSpec =
  | { kind: "preset"; preset: Preset }
  | { kind: "period"; period: Period }
  | { kind: "custom"; start: string; end: string };

const PRESET_SECONDS: Record<Exclude<Preset, "all">, number> = {
  "24h": 86400,
  "7d": 7 * 86400,
  "30d": 30 * 86400,
  "90d": 90 * 86400,
  "1y": 365 * 86400,
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function seconds(date: Date): number {
  return date.getTime() / 1000;
}

/** Return the local date of a `YYYY-MM-DD` string as [year, month index, day], or null. */
export function parseDay(text: string): [number, number, number] | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (!match) return null;
  const [year, month, day] = [Number(match[1]), Number(match[2]) - 1, Number(match[3])];
  // The Date constructor rolls invalid days over, such as Feb 30 to Mar 2.
  const date = new Date(year, month, day);
  if (date.getFullYear() !== year || date.getMonth() !== month || date.getDate() !== day) return null;
  return [year, month, day];
}

function periodBounds(period: Period, now: Date): { from: number; to: number } {
  const [y, m, d] = [now.getFullYear(), now.getMonth(), now.getDate()];
  const sunday = d - now.getDay();
  const current = (start: Date) => ({ from: seconds(start), to: seconds(now) });
  const past = (start: Date, end: Date) => ({ from: seconds(start), to: seconds(end) });
  switch (period) {
    case "today":
      return current(new Date(y, m, d));
    case "yesterday":
      return past(new Date(y, m, d - 1), new Date(y, m, d));
    case "this_week":
      return current(new Date(y, m, sunday));
    case "last_week":
      return past(new Date(y, m, sunday - 7), new Date(y, m, sunday));
    case "this_month":
      return current(new Date(y, m, 1));
    case "last_month":
      return past(new Date(y, m - 1, 1), new Date(y, m, 1));
    case "this_year":
      return current(new Date(y, 0, 1));
    case "last_year":
      return past(new Date(y - 1, 0, 1), new Date(y, 0, 1));
  }
}

/** Return the local date of a time as `YYYY-MM-DD`. */
export function localDay(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/**
 * Return the API bounds of a range at `now`, in Unix seconds. Rolling presets set only `from`,
 * and `all` sets neither. A custom range ends at local midnight after its end date, or at `now`
 * when that is earlier, so it never covers future time.
 */
export function resolveRange(spec: RangeSpec, now: Date): { from?: number; to?: number } {
  switch (spec.kind) {
    case "preset":
      return spec.preset === "all" ? {} : { from: seconds(now) - PRESET_SECONDS[spec.preset] };
    case "period":
      return periodBounds(spec.period, now);
    case "custom": {
      const start = parseDay(spec.start);
      const end = parseDay(spec.end);
      if (!start || !end) return {};
      return {
        from: seconds(new Date(start[0], start[1], start[2])),
        to: Math.min(seconds(new Date(end[0], end[1], end[2] + 1)), seconds(now)),
      };
    }
  }
}

/** Return a display name for a range, such as "Last 30 days", "This month", or "Oct 1 to Nov 17". */
export function rangeLabel(spec: RangeSpec): string {
  switch (spec.kind) {
    case "preset":
      return PRESETS.find((p) => p.value === spec.preset)?.long ?? spec.preset;
    case "period":
      return PERIODS.find((p) => p.value === spec.period)?.label ?? spec.period;
    case "custom": {
      const start = parseDay(spec.start);
      const end = parseDay(spec.end);
      if (!start || !end) return `${spec.start} to ${spec.end}`;
      const withYear = start[0] !== end[0];
      const day = ([y, m, d]: [number, number, number]) =>
        `${MONTHS[m]} ${d}${withYear ? `, ${y}` : ""}`;
      return spec.start === spec.end ? day(start) : `${day(start)} to ${day(end)}`;
    }
  }
}

/**
 * Return whether two `YYYY-MM-DD` strings are real dates with `start` on or before `end`, and,
 * when `today` is given, `end` on or before `today`.
 */
export function isValidCustom(start: string, end: string, today?: string): boolean {
  return (
    parseDay(start) !== null &&
    parseDay(end) !== null &&
    start <= end &&
    (today === undefined || end <= today)
  );
}

/** Return the range a stored value describes, or null. Bare preset strings are accepted too. */
export function parseRangeSpec(value: unknown): RangeSpec | null {
  if (typeof value === "string") {
    const preset = PRESETS.find((p) => p.value === value);
    return preset ? { kind: "preset", preset: preset.value } : null;
  }
  if (typeof value !== "object" || value === null) return null;
  const record = value as Record<string, unknown>;
  if (record.kind === "preset") {
    const preset = PRESETS.find((p) => p.value === record.preset);
    return preset ? { kind: "preset", preset: preset.value } : null;
  }
  if (record.kind === "period") {
    const period = PERIODS.find((p) => p.value === record.period);
    return period ? { kind: "period", period: period.value } : null;
  }
  if (
    record.kind === "custom" &&
    typeof record.start === "string" &&
    typeof record.end === "string" &&
    isValidCustom(record.start, record.end)
  ) {
    return { kind: "custom", start: record.start, end: record.end };
  }
  return null;
}
