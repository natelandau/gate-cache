import { describe, expect, it } from "vitest";
import { bandIndexAt, bandInset, dailyScale, FAIL_TOP, RUNS_BASE } from "./daily";
import { countTicks } from "./format";

describe("dailyScale", () => {
  it("maps the most failures to the top of the failures band, whatever the call count", () => {
    for (const runs of [0, 30, 86400]) {
      const scale = dailyScale([
        { runs, failures: 7 },
        { runs: 0, failures: 2 },
      ]);
      expect(scale.failY(7)).toBe(FAIL_TOP);
    }
  });

  it("maps the top of the gate calls scale to 1, at or above the busiest day", () => {
    const scale = dailyScale([{ runs: 600, failures: 0 }]);
    expect(scale.runsTop).toBeGreaterThanOrEqual(600);
    expect(scale.runsY(scale.runsTop)).toBe(1);
    expect(scale.runsY(600)).toBeLessThanOrEqual(1);
  });

  it("maps zero values to each band's floor", () => {
    const scale = dailyScale([{ runs: 120, failures: 3 }]);
    expect(scale.runsY(0)).toBe(RUNS_BASE);
    expect(scale.failY(0)).toBe(0);
  });

  it("stays finite when every day is zero or there are no days", () => {
    for (const days of [[{ runs: 0, failures: 0 }], []]) {
      const scale = dailyScale(days);
      expect(scale.runsY(0)).toBe(RUNS_BASE);
      expect(scale.failY(0)).toBe(0);
      for (const tick of scale.ticks) expect(Number.isFinite(tick.value)).toBe(true);
    }
  });

  it("labels the failure ticks and the gate call ticks with counts", () => {
    const scale = dailyScale([{ runs: 55, failures: 4 }]);
    expect(scale.ticks[0]).toEqual({ value: 0, label: "0" });
    expect(scale.ticks[1]).toEqual({ value: FAIL_TOP, label: "4" });
    expect(scale.ticks.slice(2).map((t) => t.label)).toEqual(["0", "20", "40", "60"]);
    expect(scale.ticks.slice(2).map((t) => t.value)).toContain(RUNS_BASE);
  });
});

describe("countTicks", () => {
  it("steps by 1, 2, or 5 times a power of ten up to at least the largest count", () => {
    expect(countTicks(55)).toEqual([0, 20, 40, 60]);
    expect(countTicks(3)).toEqual([0, 1, 2, 3]);
    expect(countTicks(400)).toEqual([0, 100, 200, 300, 400]);
  });

  it("returns whole-number ticks for an empty range", () => {
    expect(countTicks(0)).toEqual([0, 1]);
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
