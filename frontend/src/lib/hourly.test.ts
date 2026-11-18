import { describe, expect, it } from "vitest";
import type { HourCell } from "./api";
import { hourTotals, peakCell, weekdayTotals } from "./hourly";

const cells: HourCell[] = [
  { weekday: 1, hour: 9, runs: 8, saved: 30, failures: 0 },
  { weekday: 2, hour: 9, runs: 2, saved: 5, failures: 4 },
  { weekday: 2, hour: 14, runs: 5, saved: 0, failures: 1 },
];

describe("hour totals", () => {
  it("sums each hour across weekdays and each weekday across hours", () => {
    const hours = hourTotals(cells, "runs");
    expect(hours).toHaveLength(24);
    expect(hours[9]).toBe(10);
    expect(hours[14]).toBe(5);
    const days = weekdayTotals(cells, "fail");
    expect(days).toHaveLength(7);
    expect(days[2]).toBe(5);
    expect(days[0]).toBe(0);
  });

  it("finds the busiest cell, and none when every cell is zero", () => {
    expect(peakCell(cells, "runs")).toMatchObject({ weekday: 1, hour: 9 });
    expect(peakCell(cells.map((c) => ({ ...c, runs: 0 })), "runs")).toBeNull();
    expect(peakCell([], "runs")).toBeNull();
  });
});
