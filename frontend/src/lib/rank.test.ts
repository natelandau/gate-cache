import { describe, expect, it } from "vitest";
import type { FlakyGate, GateRow } from "./api";
import { outcomeShares, rankGates, rankValue, topFlaky } from "./rank";

function gate(name: string, overrides: Partial<GateRow> = {}): GateRow {
  return {
    repo: "/w/app/.git",
    repo_name: "app",
    name,
    runs: 1,
    skip_rate: null,
    avg_run: null,
    median_run: null,
    time_saved: 0,
    failures: 0,
    last_run: 0,
    flaky: false,
    ...overrides,
  };
}

const rows = [
  gate("ruff", { time_saved: 30, runs: 40, failures: 1, median_run: 2 }),
  gate("pytest", { time_saved: 500, runs: 10, failures: 4, median_run: 60 }),
  gate("ty", { time_saved: 90, runs: 25, failures: 0, median_run: null }),
  gate("e2e", { time_saved: 90, runs: 5, failures: 4, median_run: 180 }),
];

const names = (ranked: GateRow[]) => ranked.map((row) => row.name);

describe("rankValue", () => {
  it("reads the measure each ranking uses", () => {
    const row = rows[1]!;
    expect([rankValue(row, "saved"), rankValue(row, "runs"), rankValue(row, "fails")]).toEqual([500, 10, 4]);
    expect(rankValue(row, "slow")).toBe(60);
    expect(rankValue(rows[2]!, "slow")).toBeNull();
  });
});

describe("rankGates", () => {
  it("ranks by time saved, ties by name", () => {
    expect(names(rankGates(rows, "saved"))).toEqual(["pytest", "e2e", "ty", "ruff"]);
  });

  it("ranks by runs", () => {
    expect(names(rankGates(rows, "runs"))).toEqual(["ruff", "ty", "pytest", "e2e"]);
  });

  it("ranks by failures, ties by name", () => {
    expect(names(rankGates(rows, "fails"))).toEqual(["e2e", "pytest", "ruff", "ty"]);
  });

  it("ranks by median run time and skips gates without one", () => {
    expect(names(rankGates(rows, "slow"))).toEqual(["e2e", "pytest", "ruff"]);
  });

  it("returns at most `limit` rows, 8 by default", () => {
    const many = Array.from({ length: 12 }, (_, i) => gate(`g${String(i).padStart(2, "0")}`, { runs: i }));
    expect(rankGates(many, "runs")).toHaveLength(8);
    expect(names(rankGates(rows, "saved", 2))).toEqual(["pytest", "e2e"]);
  });

  it("leaves the input order alone", () => {
    const copy = [...rows];
    rankGates(rows, "runs");
    expect(rows).toEqual(copy);
  });
});

function flaky(name: string, tree_count: number): FlakyGate {
  return { repo: null, repo_name: "-", name, tree_count, last_seen: 0, trees: [] };
}

describe("topFlaky", () => {
  it("returns the five gates with the most flaky trees, ties by name", () => {
    const gates = [
      flaky("a", 1),
      flaky("f", 2),
      flaky("b", 5),
      flaky("e", 2),
      flaky("c", 3),
      flaky("d", 2),
    ];
    expect(topFlaky(gates).map((g) => g.name)).toEqual(["b", "c", "d", "e", "f"]);
  });
});

describe("outcomeShares", () => {
  it("lists every outcome in display order with its count and whole percent", () => {
    const shares = outcomeShares({ skip: 6, pass: 3, pass_unrecorded: 0, fail: 1, uncached: 0 });
    expect(shares.map((s) => [s.outcome, s.count, s.percent])).toEqual([
      ["skip", 6, "60%"],
      ["pass", 3, "30%"],
      ["pass_unrecorded", 0, "0%"],
      ["fail", 1, "10%"],
      ["uncached", 0, "0%"],
    ]);
    expect(shares[0]!.share).toBeCloseTo(0.6);
  });

  it("shows <1% for a nonzero count that rounds to zero", () => {
    const shares = outcomeShares({ skip: 999, pass: 0, pass_unrecorded: 0, fail: 1, uncached: 0 });
    expect(shares.find((s) => s.outcome === "fail")!.percent).toBe("<1%");
  });

  it("gives every outcome a zero share when nothing ran", () => {
    const shares = outcomeShares({ skip: 0, pass: 0, pass_unrecorded: 0, fail: 0, uncached: 0 });
    expect(shares.every((s) => s.share === 0 && s.percent === "0%")).toBe(true);
  });
});
