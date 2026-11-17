import { describe, expect, it } from "vitest";
import type { PreviousTotals, Summary } from "./api";
import { deltaLabel, statDeltas } from "./deltas";

const current: Summary = {
  time_saved: 100,
  unknown_saved_skips: 0,
  overhead: 0,
  waited: 0,
  net_saved: 100,
  cost_unknown_runs: 0,
  runs: 10,
  skips: 5,
  skip_rate: 0.5,
  uncached: 0,
  failures: 50,
  flaky_gates: 2,
  outcomes: { skip: 5, pass: 5, pass_unrecorded: 0, fail: 0, uncached: 0 },
  previous: null,
  daily: [],
};

const previous: PreviousTotals = {
  time_saved: 100,
  net_saved: 100,
  runs: 10,
  skips: 5,
  skip_rate: 0.5,
  failures: 50,
  flaky_gates: 2,
  days: 30,
};

describe("statDeltas", () => {
  it("shows time saved as a percentage, up is good", () => {
    const deltas = statDeltas({ ...current, time_saved: 118 }, previous);
    expect(deltas.time_saved).toEqual({ text: "▲ 18%", tone: "good" });
  });

  it("shows net saved as an absolute duration, even across zero", () => {
    const deltas = statDeltas({ ...current, net_saved: -20 }, previous);
    expect(deltas.net_saved).toEqual({ text: "▼ 2m 0s", tone: "bad" });
  });

  it("leaves net saved out when the previous window has no comparable value", () => {
    expect(statDeltas(current, { ...previous, net_saved: null }).net_saved).toBeUndefined();
  });

  it("shows failures as a percentage, up is bad", () => {
    const deltas = statDeltas({ ...current, failures: 56 }, previous);
    expect(deltas.failures).toEqual({ text: "▲ 12%", tone: "bad" });
  });

  it("shows skip rate in percentage points", () => {
    const deltas = statDeltas(
      { ...current, skip_rate: 0.71 },
      { ...previous, skip_rate: 0.67 },
    );
    expect(deltas.skip_rate).toEqual({ text: "▲ 4 pts", tone: "good" });
  });

  it("shows flaky gates as an absolute count, down is good", () => {
    const deltas = statDeltas({ ...current, flaky_gates: 3 }, { ...previous, flaky_gates: 4 });
    expect(deltas.flaky_gates).toEqual({ text: "▼ 1", tone: "good" });
  });

  it("shows an absolute change when the previous value is zero", () => {
    const deltas = statDeltas({ ...current, runs: 5 }, { ...previous, runs: 0 });
    expect(deltas.runs).toEqual({ text: "▲ 5", tone: "good" });
  });

  it("shows a drop in runs as bad", () => {
    const deltas = statDeltas({ ...current, runs: 8 }, previous);
    expect(deltas.runs).toEqual({ text: "▼ 20%", tone: "bad" });
  });

  it("says no change when the values are equal", () => {
    const deltas = statDeltas(current, previous);
    for (const delta of Object.values(deltas)) {
      expect(delta).toEqual({ text: "No change", tone: "neutral" });
    }
  });

  it("shows a real change that rounds to zero as under one percent", () => {
    const up = statDeltas({ ...current, time_saved: 100.4 }, previous);
    expect(up.time_saved).toEqual({ text: "▲ <1%", tone: "good" });
    const down = statDeltas({ ...current, failures: 49.9 }, previous);
    expect(down.failures).toEqual({ text: "▼ <1%", tone: "good" });
  });

  it("shows a one point skip rate change in the singular", () => {
    const deltas = statDeltas({ ...current, skip_rate: 0.51 }, previous);
    expect(deltas.skip_rate).toEqual({ text: "▲ 1 pt", tone: "good" });
  });

  it("shows a real skip rate change that rounds to zero as under one point", () => {
    const deltas = statDeltas({ ...current, skip_rate: 0.498 }, previous);
    expect(deltas.skip_rate).toEqual({ text: "▼ <1 pt", tone: "bad" });
  });

  it("leaves skip rate out when either period has no rate", () => {
    expect(statDeltas({ ...current, skip_rate: null }, previous).skip_rate).toBeUndefined();
    expect(statDeltas(current, { ...previous, skip_rate: null }).skip_rate).toBeUndefined();
  });
});

describe("deltaLabel", () => {
  it("names the previous window in days, rounded up", () => {
    expect(deltaLabel({ ...previous, days: 30 })).toBe("vs prev 30d");
    expect(deltaLabel({ ...previous, days: 16.4 })).toBe("vs prev 17d");
  });

  it("names a window under two days in hours", () => {
    expect(deltaLabel({ ...previous, days: 0.375 })).toBe("vs prev 9h");
    expect(deltaLabel({ ...previous, days: 1 })).toBe("vs prev 24h");
    expect(deltaLabel({ ...previous, days: 0.001 })).toBe("vs prev 1h");
  });
});
