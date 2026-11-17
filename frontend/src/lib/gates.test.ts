import { describe, expect, it } from "vitest";
import type { EventRow, GateRow } from "./api";
import { findGate, gateKey, tally, trendStats } from "./gates";

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
