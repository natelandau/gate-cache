import { describe, expect, it } from "vitest";
import { sparkPath, valueParts } from "./sparkline";

const ys = (path: string) => [...path.matchAll(/[ML]\s*[\d.]+\s+([\d.]+)/g)].map((m) => Number(m[1]));

describe("sparkPath", () => {
  it("draws nothing broken for an empty series", () => {
    const { line, area } = sparkPath([], 200, 34);
    expect(line).not.toContain("NaN");
    expect(area).not.toContain("NaN");
  });

  it("draws an all-zero series as a flat line near the bottom", () => {
    const { line } = sparkPath([0, 0, 0], 200, 34);
    const points = ys(line);
    expect(points).toHaveLength(3);
    expect(new Set(points).size).toBe(1);
    expect(points[0]).toBeGreaterThan(30);
  });

  it("breaks the line at a missing value", () => {
    const { line } = sparkPath([1, null, 3], 200, 34);
    expect(line.match(/M/g)).toHaveLength(2);
  });

  it("puts the largest value at the top", () => {
    const points = ys(sparkPath([0, 5, 10], 200, 34).line);
    expect(points[2]).toBeLessThan(points[1]!);
    expect(points[1]).toBeLessThan(points[0]!);
  });
});

describe("valueParts", () => {
  it("splits units from the digits of a duration", () => {
    expect(valueParts("6h 38m")).toEqual([
      { text: "6", unit: false },
      { text: "h", unit: true },
      { text: " ", unit: false },
      { text: "38", unit: false },
      { text: "m", unit: true },
    ]);
  });

  it("treats a percent sign as a unit and leaves a plain count whole", () => {
    expect(valueParts("61%")).toEqual([
      { text: "61", unit: false },
      { text: "%", unit: true },
    ]);
    expect(valueParts("1,705")).toEqual([{ text: "1,705", unit: false }]);
  });

  it("keeps a sign with its number", () => {
    expect(valueParts("−2m")[0]).toEqual({ text: "−2", unit: false });
  });
});
