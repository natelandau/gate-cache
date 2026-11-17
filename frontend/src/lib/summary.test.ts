import { describe, expect, it } from "vitest";
import type { Summary } from "./api";
import { summaryNote, summaryStats } from "./summary";

const base: Summary = {
  time_saved: 90,
  unknown_saved_skips: 0,
  runs: 12,
  skips: 1,
  skip_rate: 0.5,
  uncached: 0,
  failures: 0,
  flaky_gates: 0,
  outcomes: { skip: 1, pass: 1, pass_unrecorded: 0, fail: 0, uncached: 0 },
  previous: null,
  daily: [],
};

describe("summaryStats", () => {
  it("lists the headline numbers in order", () => {
    const stats = summaryStats(base);
    expect(stats.map((s) => [s.label, s.value])).toEqual([
      ["Time saved", "1m 30s"],
      ["Runs", "12"],
      ["Skip rate", "50%"],
      ["Flaky gates", "0"],
      ["Failures", "0"],
    ]);
    expect(stats[1]?.hint).toBeUndefined();
    expect(stats[2]?.hint).toBe("1 skip");
  });

  it("flags problems and links flaky gates only when given a link", () => {
    const summary = { ...base, uncached: 2, failures: 3, flaky_gates: 1 };
    const linked = summaryStats(summary, { flakyHref: "#/flaky" });
    expect(linked[1]?.hint).toBe("2 uncached");
    expect(linked[3]).toMatchObject({ tone: "flaky", href: "#/flaky" });
    expect(linked[4]).toMatchObject({ tone: "danger" });
    expect(summaryStats(summary)[3]?.href).toBeUndefined();
  });
});

describe("summaryStats deltas", () => {
  it("leaves deltas off when there is no previous window", () => {
    expect(summaryStats(base).every((s) => s.delta === undefined)).toBe(true);
  });

  it("attaches a delta to every stat when there is a previous window", () => {
    const previous = { ...base, days: 30, runs: 6 };
    const stats = summaryStats({ ...base, previous });
    expect(stats.map((s) => s.delta?.text)).toEqual([
      "No change",
      "▲ 100%",
      "No change",
      "No change",
      "No change",
    ]);
  });
});

describe("summaryNote", () => {
  it("explains skips without a duration", () => {
    expect(summaryNote(base)).toBeUndefined();
    expect(summaryNote({ ...base, unknown_saved_skips: 1 })).toBe(
      "1 skip had no recorded duration, so it adds nothing to time saved.",
    );
    expect(summaryNote({ ...base, unknown_saved_skips: 2 })).toBe(
      "2 skips had no recorded duration, so they add nothing to time saved.",
    );
  });
});
