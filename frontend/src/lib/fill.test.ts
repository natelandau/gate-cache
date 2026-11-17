import { describe, expect, it } from "vitest";
import { dayKey, fillDays } from "./fill";

const UTC = "UTC";
// 2026-11-10T00:00:00Z
const NOV10 = 1_794_268_800;

describe("dayKey", () => {
  it("formats a timestamp as a day in the given zone", () => {
    expect(dayKey(NOV10, UTC)).toBe("2026-11-10");
    // Midnight UTC is still the previous evening in New York.
    expect(dayKey(NOV10, "America/New_York")).toBe("2026-11-09");
  });
});

describe("fillDays", () => {
  it("inserts zero days between and around recorded days", () => {
    const daily = [{ day: "2026-11-11", saved: 5, failures: 1, runs: 3 }];
    const out = fillDays(daily, NOV10, NOV10 + 3 * 86400, UTC);
    expect(out).toEqual([
      { day: "2026-11-10", saved: 0, failures: 0, runs: 0 },
      { day: "2026-11-11", saved: 5, failures: 1, runs: 3 },
      { day: "2026-11-12", saved: 0, failures: 0, runs: 0 },
    ]);
  });

  it("treats the end bound as exclusive", () => {
    const out = fillDays([], NOV10, NOV10 + 86400, UTC);
    expect(out.map((d) => d.day)).toEqual(["2026-11-10"]);
  });

  it("starts at the first data day when there is no lower bound", () => {
    const daily = [
      { day: "2026-11-10", saved: 1, failures: 0, runs: 1 },
      { day: "2026-11-12", saved: 2, failures: 0, runs: 1 },
    ];
    const out = fillDays(daily, undefined, NOV10 + 4 * 86400, UTC);
    expect(out.map((d) => d.day)).toEqual(["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"]);
  });

  it("returns nothing when unbounded and empty", () => {
    expect(fillDays([], undefined, NOV10, UTC)).toEqual([]);
  });

  it("walks calendar days across a DST change", () => {
    // 2026-11-01 is the US fall-back day, a 25 hour day in New York.
    const start = 1_793_419_200; // 2026-10-31T04:00:00Z, midnight in New York
    const out = fillDays([], start, start + 3 * 86400, "America/New_York");
    expect(out.map((d) => d.day)).toEqual(["2026-10-31", "2026-11-01", "2026-11-02"]);
  });

  it("keeps recorded days outside the bounds rather than dropping data", () => {
    const daily = [{ day: "2026-11-09", saved: 1, failures: 0, runs: 1 }];
    const out = fillDays(daily, NOV10, NOV10 + 86400, UTC);
    expect(out.map((d) => d.day)).toEqual(["2026-11-09", "2026-11-10"]);
  });
});
