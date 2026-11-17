import { describe, expect, it } from "vitest";
import { dailyScale, FAIL_TOP, SAVED_BASE } from "./daily";

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
