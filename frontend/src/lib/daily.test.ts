import { describe, expect, it } from "vitest";
import { bandIndexAt, bandInset, dailyScale, FAIL_TOP, SAVED_BASE } from "./daily";

describe("dailyScale", () => {
  it("maps the most failures to the top of the failures band, whatever was saved", () => {
    for (const saved of [0, 30, 86400]) {
      const scale = dailyScale([
        { saved, failures: 7 },
        { saved: 0, failures: 2 },
      ]);
      expect(scale.failY(7)).toBe(FAIL_TOP);
    }
  });

  it("maps the top of the time-saved scale to 1, at or above the busiest day", () => {
    const scale = dailyScale([{ saved: 600, failures: 0 }]);
    expect(scale.savedTop).toBeGreaterThanOrEqual(600);
    expect(scale.savedY(scale.savedTop)).toBe(1);
    expect(scale.savedY(600)).toBeLessThanOrEqual(1);
  });

  it("maps zero values to each band's floor", () => {
    const scale = dailyScale([{ saved: 120, failures: 3 }]);
    expect(scale.savedY(0)).toBe(SAVED_BASE);
    expect(scale.failY(0)).toBe(0);
  });

  it("stays finite when every day is zero or there are no days", () => {
    for (const days of [[{ saved: 0, failures: 0 }], []]) {
      const scale = dailyScale(days);
      expect(scale.savedY(0)).toBe(SAVED_BASE);
      expect(scale.failY(0)).toBe(0);
      for (const tick of scale.ticks) expect(Number.isFinite(tick.value)).toBe(true);
    }
  });

  it("labels the failure ticks with counts and the saved ticks with durations", () => {
    const scale = dailyScale([{ saved: 600, failures: 4 }]);
    expect(scale.ticks[0]).toEqual({ value: 0, label: "0" });
    expect(scale.ticks[1]).toEqual({ value: FAIL_TOP, label: "4" });
    expect(scale.ticks.slice(2).map((t) => t.value)).toContain(SAVED_BASE);
  });
});

describe("bandInset", () => {
  it("returns the outer padding of a padded band scale as a percent of the width", () => {
    // d3 scaleBand().padding(0.25) over 3 bands: step = width / 3.25, centered columns start at step / 8.
    expect(bandInset(3, 0.25)).toBeCloseTo((0.125 / 3.25) * 100);
    expect(bandInset(0, 0.25)).toBe(0);
  });
});

describe("bandIndexAt", () => {
  it("maps a position across the plot to the day under it", () => {
    expect(bandIndexAt(0.01, 3, 0.25)).toBe(0);
    expect(bandIndexAt(0.5, 3, 0.25)).toBe(1);
    expect(bandIndexAt(0.99, 3, 0.25)).toBe(2);
  });

  it("clamps the outer padding to the nearest day and rejects positions off the plot", () => {
    expect(bandIndexAt(0, 3, 0.25)).toBe(0);
    expect(bandIndexAt(1, 3, 0.25)).toBe(2);
    expect(bandIndexAt(-0.1, 3, 0.25)).toBeNull();
    expect(bandIndexAt(1.1, 3, 0.25)).toBeNull();
    expect(bandIndexAt(0.5, 0, 0.25)).toBeNull();
  });
});
