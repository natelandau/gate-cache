import { describe, expect, it } from "vitest";
import type { EventRow, GateRow } from "./api";
import { findGate, gateKey, histogramBars, sourceParts, splitGateName, tally, trendStats } from "./gates";

describe("gateKey", () => {
  it("separates gates of the same name in different repos", () => {
    expect(gateKey({ repo: "/a/.git", name: "lint" })).not.toBe(gateKey({ repo: null, name: "lint" }));
  });
});

describe("findGate", () => {
  it("matches on repo and name, treating null as its own repo", () => {
    const rows = [
      { repo: null, name: "lint" },
      { repo: "/a/.git", name: "lint" },
    ] as GateRow[];
    expect(findGate(rows, { repo: "/a/.git", name: "lint" })).toBe(rows[1]);
    expect(findGate(rows, { repo: null, name: "lint" })).toBe(rows[0]);
    expect(findGate(rows, { repo: null, name: "test" })).toBeUndefined();
    expect(findGate(undefined, { repo: null, name: "lint" })).toBeUndefined();
  });
});

describe("trendStats", () => {
  it("returns the count, median, and latest pass duration", () => {
    const trend = [
      { ts: 1, duration: 10 },
      { ts: 2, duration: 30 },
      { ts: 3, duration: 20 },
      { ts: 4, duration: 40 },
    ];
    expect(trendStats(trend)).toEqual({ count: 4, median: 25, latest: 40 });
  });

  it("returns nulls for no passes", () => {
    expect(trendStats([])).toEqual({ count: 0, median: null, latest: null });
  });
});

describe("tally", () => {
  it("counts fails and passes, with unrecorded passes as passes", () => {
    const runs = ["fail", "pass", "pass_unrecorded", "skip", "fail"].map(
      (outcome) => ({ outcome }) as EventRow,
    );
    expect(tally(runs)).toEqual({ fails: 2, passes: 2 });
  });
});

describe("histogramBars", () => {
  const edges = Array.from({ length: 13 }, (_, i) => 2 + i);
  const counts = Array.from({ length: 12 }, (_, i) => i);

  it("returns one labeled bar per bin, carrying the counts", () => {
    const bars = histogramBars({ edges, counts, median: 5, p90: 9 });
    expect(bars).toHaveLength(12);
    expect(bars[0]).toEqual({ from: 2, to: 3, count: 0, label: "2s–3s" });
    expect(bars.map((b) => b.count)).toEqual(counts);
  });
});

describe("sourceParts", () => {
  it("rounds seconds, colors the first five, and folds the rest into Other", () => {
    const rows = Array.from({ length: 7 }, (_, i) => ({
      key: `k${i}`,
      label: `L${i}`,
      title: i === 0 ? "T" : null,
      runs: 1,
      time_spent: 10.6 + i,
    }));
    const parts = sourceParts(rows);
    expect(parts[0]).toMatchObject({ key: "k0", label: "L0", count: 11, color: "var(--chart-series-1)", title: "T" });
    expect(parts[4]!.color).toBe("var(--chart-series-5)");
    expect(parts).toHaveLength(6);
    expect(parts[5]).toMatchObject({ key: "other", label: "Other", count: 32, color: "var(--chart-neutral)", title: "L5, L6" });
  });
});

describe("splitGateName", () => {
  it("splits off a trailing @ and hex suffix", () => {
    expect(splitGateName("apple-test@c350b4abb3f3")).toEqual({ base: "apple-test", suffix: "@c350b4abb3f3" });
  });

  it("leaves other names whole", () => {
    expect(splitGateName("ruff format --check")).toEqual({ base: "ruff format --check", suffix: "" });
    expect(splitGateName("deploy@prod")).toEqual({ base: "deploy@prod", suffix: "" });
  });
});
