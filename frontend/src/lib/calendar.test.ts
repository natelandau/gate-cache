import { describe, expect, it } from "vitest";
import { calendarFacts, calendarLayout, chunkWeeks } from "./calendar";
import type { DayBucket } from "./fill";

function range(from: string, count: number): string[] {
  const start = new Date(`${from}T00:00:00Z`);
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(start);
    d.setUTCDate(d.getUTCDate() + i);
    return d.toISOString().slice(0, 10);
  });
}

const bucket = (day: string, runs: number): DayBucket => ({
  day,
  saved: 0,
  failures: 0,
  runs,
  spent: 0,
  skips: 0,
  ran: 0,
  spot_checks: 0,
  spot_check_failures: 0,
});

describe("calendarLayout", () => {
  it("lays out up to six weeks as a month grid and longer ranges as week columns", () => {
    expect(calendarLayout(range("2026-10-19", 30))).toBe("month");
    expect(calendarLayout(range("2026-10-07", 42))).toBe("month");
    expect(calendarLayout(range("2026-08-20", 90))).toBe("weeks");
  });
});

describe("chunkWeeks", () => {
  it("splits days into weeks and pads the first and last week", () => {
    // 2026-10-19 is a Monday, so a Monday-first grid needs no lead.
    const grid = chunkWeeks(range("2026-10-19", 30), 0);
    expect(grid).toHaveLength(5);
    expect(grid[0]![0]).toBe("2026-10-19");
    expect(grid[4]).toEqual(["2026-11-16", "2026-11-17", null, null, null, null, null]);
  });

  it("pads before a range that starts midweek", () => {
    expect(chunkWeeks(["2026-11-04"], 2)[0]).toEqual([null, null, "2026-11-04", null, null, null, null]);
  });

  it("returns no weeks for no days", () => {
    expect(chunkWeeks([], 3)).toEqual([]);
  });
});

describe("calendarFacts", () => {
  it("finds the busiest day and counts active days", () => {
    const facts = calendarFacts([bucket("2026-11-01", 3), bucket("2026-11-02", 0), bucket("2026-11-03", 9)]);
    expect(facts.busiest?.day).toBe("2026-11-03");
    expect(facts.activeDays).toBe(2);
    expect(facts.totalDays).toBe(3);
    expect(facts.runsPerActiveDay).toBe(6);
  });

  it("has no busiest day or average when nothing ran", () => {
    const facts = calendarFacts([bucket("2026-11-01", 0)]);
    expect(facts.busiest).toBeNull();
    expect(facts.runsPerActiveDay).toBeNull();
    expect(calendarFacts([]).busiest).toBeNull();
  });
});
