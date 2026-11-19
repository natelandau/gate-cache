import { describe, expect, it } from "vitest";
import type { GateRow, TriageItem } from "./api";
import { gateRunText, partShares, rankGates, rankValue, topFlaky } from "./rank";

function gate(name: string, overrides: Partial<GateRow> = {}): GateRow {
  return {
    repo: "/w/app/.git",
    repo_name: "app",
    name,
    runs: 1,
    skip_rate: null,
    avg_run: null,
    median_run: null,
    p90_run: null,
    time_saved: 0,
    time_spent: 0,
    fail_time: 0,
    cpu_ratio: null,
    peak_rss: null,
    median_rss: null,
    failures: 0,
    spot_checks: 0,
    spot_check_failures: 0,
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

describe("gateRunText", () => {
  it("joins the average and median run time", () => {
    expect(gateRunText(gate("x", { avg_run: 3, median_run: 2 }))).toBe("avg run 3s \u00b7 median 2s");
  });

  it("is empty without a median", () => {
    expect(gateRunText(gate("x", { avg_run: 3, median_run: null }))).toBe("");
  });
});

describe("rankGates", () => {
  it("orders by time spent, ties by name", () => {
    const spent = [
      gate("b", { time_spent: 10 }),
      gate("a", { time_spent: 10 }),
      gate("c", { time_spent: 99 }),
    ];
    expect(names(rankGates(spent, "spent"))).toEqual(["c", "a", "b"]);
  });

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

function flaky(name: string, treeCount: number): TriageItem {
  const trees = Array.from({ length: treeCount }, (_, i) => ({ tree: `t${i}`, runs: [] }));
  return {
    repo: null,
    repo_name: "-",
    name,
    reason: "flaky",
    last_seen: 0,
    evidence: { trees, tests: [], retried: [] },
  };
}

describe("topFlaky", () => {
  it("returns the five flaky gates with the most flaky trees, ties by name", () => {
    const spot: TriageItem = {
      repo: null,
      repo_name: "-",
      name: "z",
      reason: "failed_spot_check",
      last_seen: 0,
      evidence: { count: 9, runs: [] },
    };
    const gates = [
      spot,
      flaky("a", 1),
      flaky("f", 2),
      flaky("b", 5),
      flaky("e", 2),
      flaky("c", 3),
      flaky("d", 2),
    ];
    expect(topFlaky(gates).map((g) => g.name)).toEqual(["b", "c", "d", "e", "f"]);
  });

  it("leaves out gates with no flaky tree, such as gates with only retried tests", () => {
    expect(topFlaky([flaky("a", 0), flaky("b", 1)]).map((g) => g.name)).toEqual(["b"]);
  });
});

describe("partShares", () => {
  it("lists every part in order with its count and whole percent", () => {
    const counts = { skip: 6, pass: 3, pass_unrecorded: 0, fail: 1, uncached: 0 };
    const shares = partShares(Object.keys(counts) as (keyof typeof counts)[], (k) => counts[k]);
    expect(shares.map((s) => [s.part, s.count, s.percent])).toEqual([
      ["skip", 6, "60%"],
      ["pass", 3, "30%"],
      ["pass_unrecorded", 0, "0%"],
      ["fail", 1, "10%"],
      ["uncached", 0, "0%"],
    ]);
    expect(shares[0]!.share).toBeCloseTo(0.6);
  });

  it("shows <1% for a nonzero count that rounds to zero", () => {
    const shares = partShares([999, 0, 1], (n) => n);
    expect(shares[2]!.percent).toBe("<1%");
  });

  it("gives every part a zero share when the total is zero", () => {
    const shares = partShares([0, 0, 0], (n) => n);
    expect(shares.every((s) => s.share === 0 && s.percent === "0%")).toBe(true);
  });
});
