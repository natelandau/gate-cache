import { describe, expect, it } from "vitest";
import { isValidCustom, localDay, parseRangeSpec, rangeLabel, resolveRange } from "./range";

/** Return a local time in Unix seconds. */
function local(y: number, m: number, d: number, h = 0): number {
  return new Date(y, m - 1, d, h).getTime() / 1000;
}

// Tuesday 2026-11-17 15:00 local.
const now = new Date(2026, 10, 17, 15);
const nowSec = now.getTime() / 1000;

describe("resolveRange", () => {
  it("starts presets their length before now and leaves all time unbounded", () => {
    expect(resolveRange({ kind: "preset", preset: "1y" }, now)).toEqual({ from: nowSec - 365 * 86400 });
    expect(resolveRange({ kind: "preset", preset: "24h" }, now)).toEqual({ from: nowSec - 86400 });
    expect(resolveRange({ kind: "preset", preset: "7d" }, now)).toEqual({ from: nowSec - 7 * 86400 });
    expect(resolveRange({ kind: "preset", preset: "all" }, now)).toEqual({});
  });

  it("ends current periods now", () => {
    expect(resolveRange({ kind: "period", period: "today" }, now)).toEqual({
      from: local(2026, 11, 17),
      to: nowSec,
    });
    expect(resolveRange({ kind: "period", period: "this_week" }, now)).toEqual({
      from: local(2026, 11, 15),
      to: nowSec,
    });
    expect(resolveRange({ kind: "period", period: "this_month" }, now)).toEqual({
      from: local(2026, 11, 1),
      to: nowSec,
    });
    expect(resolveRange({ kind: "period", period: "this_year" }, now)).toEqual({
      from: local(2026, 1, 1),
      to: nowSec,
    });
  });

  it("covers past periods whole, with weeks starting Sunday", () => {
    expect(resolveRange({ kind: "period", period: "yesterday" }, now)).toEqual({
      from: local(2026, 11, 16),
      to: local(2026, 11, 17),
    });
    expect(resolveRange({ kind: "period", period: "last_week" }, now)).toEqual({
      from: local(2026, 11, 8),
      to: local(2026, 11, 15),
    });
    expect(resolveRange({ kind: "period", period: "last_month" }, now)).toEqual({
      from: local(2026, 10, 1),
      to: local(2026, 11, 1),
    });
    expect(resolveRange({ kind: "period", period: "last_year" }, now)).toEqual({
      from: local(2025, 1, 1),
      to: local(2026, 1, 1),
    });
  });

  it("starts the week on the same Sunday when today is Sunday", () => {
    const sunday = new Date(2026, 10, 15, 9);
    expect(resolveRange({ kind: "period", period: "this_week" }, sunday).from).toBe(local(2026, 11, 15));
  });

  it("starts this week on the Sunday before, across month and year boundaries", () => {
    const tuesday = new Date(2026, 11, 1, 12);
    expect(resolveRange({ kind: "period", period: "this_week" }, tuesday).from).toBe(local(2026, 11, 29));
    const friday = new Date(2027, 0, 1, 12);
    expect(resolveRange({ kind: "period", period: "this_week" }, friday).from).toBe(local(2026, 12, 27));
  });

  it("crosses a year boundary for last month in January", () => {
    const january = new Date(2027, 0, 10);
    expect(resolveRange({ kind: "period", period: "last_month" }, january)).toEqual({
      from: local(2026, 12, 1),
      to: local(2027, 1, 1),
    });
  });

  it("ends a custom range at local midnight after its end date", () => {
    expect(resolveRange({ kind: "custom", start: "2026-10-01", end: "2026-11-16" }, now)).toEqual({
      from: local(2026, 10, 1),
      to: local(2026, 11, 17),
    });
  });

  it("ends a custom range that includes today now, so it draws no future days", () => {
    expect(resolveRange({ kind: "custom", start: "2026-11-10", end: "2026-11-17" }, now)).toEqual({
      from: local(2026, 11, 10),
      to: nowSec,
    });
    expect(resolveRange({ kind: "custom", start: "2026-11-10", end: "2026-11-30" }, now).to).toBe(nowSec);
  });

  it("keeps day boundaries local across a daylight saving change", () => {
    // America/New_York leaves daylight saving time on 2026-11-01.
    const { from, to } = resolveRange({ kind: "custom", start: "2026-11-01", end: "2026-11-01" }, now);
    expect((to ?? 0) - (from ?? 0)).toBe(25 * 3600);
  });
});

describe("rangeLabel", () => {
  it("names presets, periods, and custom ranges", () => {
    expect(rangeLabel({ kind: "preset", preset: "30d" })).toBe("Last 30 days");
    expect(rangeLabel({ kind: "preset", preset: "1y" })).toBe("Last 12 months");
    expect(rangeLabel({ kind: "period", period: "last_year" })).toBe("Last year");
    expect(rangeLabel({ kind: "preset", preset: "all" })).toBe("All time");
    expect(rangeLabel({ kind: "period", period: "this_month" })).toBe("This month");
    expect(rangeLabel({ kind: "custom", start: "2026-10-01", end: "2026-11-17" })).toBe("Oct 1 to Nov 17");
  });

  it("names one custom day once, and adds years when they differ", () => {
    expect(rangeLabel({ kind: "custom", start: "2026-11-17", end: "2026-11-17" })).toBe("Nov 17");
    expect(rangeLabel({ kind: "custom", start: "2025-12-20", end: "2026-01-05" })).toBe(
      "Dec 20, 2025 to Jan 5, 2026",
    );
  });
});

describe("isValidCustom", () => {
  it("needs two real dates in order", () => {
    expect(isValidCustom("2026-11-01", "2026-11-17")).toBe(true);
    expect(isValidCustom("2026-11-17", "2026-11-17")).toBe(true);
    expect(isValidCustom("2026-11-17", "2026-11-01")).toBe(false);
    expect(isValidCustom("", "2026-11-01")).toBe(false);
    expect(isValidCustom("2026-02-30", "2026-03-01")).toBe(false);
    expect(isValidCustom("2026-1-5", "2026-03-01")).toBe(false);
  });

  it("rejects an end after today when today is given", () => {
    expect(isValidCustom("2026-11-01", "2026-11-17", "2026-11-17")).toBe(true);
    expect(isValidCustom("2026-11-01", "2026-11-18", "2026-11-17")).toBe(false);
  });
});

describe("localDay", () => {
  it("formats the local date of a time as YYYY-MM-DD", () => {
    expect(localDay(now)).toBe("2026-11-17");
    expect(localDay(new Date(2027, 0, 5, 23, 30))).toBe("2027-01-05");
  });
});

describe("parseRangeSpec", () => {
  it("accepts the old bare preset strings", () => {
    expect(parseRangeSpec("7d")).toEqual({ kind: "preset", preset: "7d" });
    expect(parseRangeSpec("all")).toEqual({ kind: "preset", preset: "all" });
    expect(parseRangeSpec("2w")).toBeNull();
  });

  it("accepts valid specs and rejects malformed ones", () => {
    expect(parseRangeSpec({ kind: "preset", preset: "1y" })).toEqual({ kind: "preset", preset: "1y" });
    expect(parseRangeSpec({ kind: "period", period: "last_week" })).toEqual({
      kind: "period",
      period: "last_week",
    });
    expect(parseRangeSpec({ kind: "custom", start: "2026-10-01", end: "2026-11-17", extra: 1 })).toEqual({
      kind: "custom",
      start: "2026-10-01",
      end: "2026-11-17",
    });
    expect(parseRangeSpec({ kind: "custom", start: "x", end: "y" })).toBeNull();
    expect(parseRangeSpec({ kind: "period", period: "next_week" })).toBeNull();
    expect(parseRangeSpec(null)).toBeNull();
    expect(parseRangeSpec(42)).toBeNull();
  });
});
