import { describe, expect, it } from "vitest";
import { formatDuration } from "./format";
import {
  formatHeatValue,
  HEAT_OPTIONS,
  heatColor,
  heatStep,
  heatValue,
  weekdayName,
} from "./heat";

describe("heatStep", () => {
  it("returns 0 for no activity", () => {
    expect(heatStep(0, 10)).toBe(0);
  });

  it("puts the smallest nonzero value in step 1", () => {
    expect(heatStep(1, 10)).toBe(1);
  });

  it("puts the maximum in step 5", () => {
    expect(heatStep(10, 10)).toBe(5);
  });

  it("returns 0 when the maximum is 0", () => {
    expect(heatStep(0, 0)).toBe(0);
  });
});

describe("heatColor", () => {
  it("names the ramp step for the metric", () => {
    expect(heatColor("saved", 3)).toBe("var(--heat-saved-3)");
  });

  it("uses the empty token for step 0", () => {
    expect(heatColor("runs", 0)).toBe("var(--heat-empty)");
  });
});

describe("heatValue", () => {
  const bucket = { runs: 4, saved: 90, failures: 1 };

  it("reads the field for each metric", () => {
    expect(heatValue(bucket, "runs")).toBe(4);
    expect(heatValue(bucket, "saved")).toBe(90);
    expect(heatValue(bucket, "fail")).toBe(1);
  });
});

describe("formatHeatValue", () => {
  it("formats time saved as a duration and counts as numbers", () => {
    expect(formatHeatValue("saved", 90)).toBe(formatDuration(90));
    expect(formatHeatValue("fail", 1200)).toBe("1,200");
  });
});

describe("HEAT_OPTIONS", () => {
  it("lists runs, time saved, and failures with their labels", () => {
    expect(HEAT_OPTIONS).toEqual([
      { value: "runs", label: "Runs" },
      { value: "saved", label: "Time saved" },
      { value: "fail", label: "Failures" },
    ]);
  });
});

describe("weekdayName", () => {
  it("starts the week on Sunday", () => {
    const sunday = new Date(2026, 10, 15);
    expect(weekdayName(0, "long")).toBe(sunday.toLocaleString(undefined, { weekday: "long" }));
    expect(weekdayName(3, "short")).toBe(
      new Date(2026, 10, 18).toLocaleString(undefined, { weekday: "short" }),
    );
  });
});
