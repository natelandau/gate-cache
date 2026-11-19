import { describe, expect, it } from "vitest";
import { sparkDomain, sparkPath } from "./sparkline";

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

  it("draws a known day with no known neighbors, instead of a bare move", () => {
    const { line } = sparkPath([1, null, 3], 200, 34);
    // Every subpath must draw after its move, or the browser paints nothing for it.
    expect(line.split("M").slice(1).every((sub) => /[LHVlhv]/.test(sub))).toBe(true);
  });

  it("keeps negative values inside the box, with zero above the lowest point", () => {
    const points = ys(sparkPath([-10, 0, 10], 200, 34).line);
    for (const y of points) {
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(34);
    }
    expect(points[0]).toBeGreaterThan(points[1]!);
    expect(points[1]).toBeGreaterThan(points[2]!);
  });

  it("puts the largest value at the top", () => {
    const points = ys(sparkPath([0, 5, 10], 200, 34).line);
    expect(points[2]).toBeLessThan(points[1]!);
    expect(points[1]).toBeLessThan(points[0]!);
  });

  it("closes the area at zero when the series goes negative", () => {
    // Zero sits halfway between -10 and 10, so the area closes there, not at the bottom.
    const { area } = sparkPath([-10, 10], 200, 34);
    expect(area).not.toContain(" 34 ");
    expect(area).not.toMatch(/L\d+ 34\b/);
  });

  it("draws series that share a domain on one scale", () => {
    const series = [[0, 10], [0, 5]];
    const domain = sparkDomain(series);
    const [ran, failed] = series.map((values) => ys(sparkPath(values, 200, 34, domain).line));
    expect(ran![0]).toBe(failed![0]);
    // Half the peak sits halfway between the zero line and the peak.
    expect(failed![1]).toBeCloseTo((ran![0]! + ran![1]!) / 2, 0);
  });
});
