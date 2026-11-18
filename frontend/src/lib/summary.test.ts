import { describe, expect, it } from "vitest";
import type { Summary } from "./api";
import type { DayBucket } from "./fill";
import { pickedRange, summaryNote, summaryStats } from "./summary";

const base: Summary = {
  time_saved: 90,
  time_spent: 60,
  fail_time: 0,
  unknown_saved_skips: 0,
  overhead: 0,
  waited: 0,
  net_saved: 90,
  cost_unknown_runs: 0,
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
      ["Net saved", "1m 30s"],
      ["Time spent", "1m 0s"],
      ["Runs", "12"],
      ["Skip rate", "50%"],
      ["Flaky gates", "0"],
      ["Failures", "0"],
    ]);
    expect(stats[3]?.hint).toBeUndefined();
    expect(stats[4]?.hint).toBe("1 skip");
  });

  it("flags problems and links flaky gates only when given a link", () => {
    const summary = { ...base, uncached: 2, failures: 3, flaky_gates: 1 };
    const linked = summaryStats(summary, { flakyHref: "#/flaky" });
    expect(linked[3]?.hint).toBe("2 uncached");
    expect(linked[5]).toMatchObject({ tone: "flaky", href: "#/flaky" });
    expect(linked[6]).toMatchObject({ tone: "danger" });
    expect(summaryStats(summary)[5]?.href).toBeUndefined();
  });
});

describe("net saved", () => {
  it("names what it subtracts and explains the sum in its title", () => {
    const stat = summaryStats({ ...base, overhead: 3, waited: 60, net_saved: 27 })[1];
    expect(stat).toMatchObject({
      label: "Net saved",
      value: "27s",
      hint: "minus 1m 3s overhead and waits",
      tone: "default",
    });
    expect(stat?.title).toContain("Time saved minus");
  });

  it("hints at the time failed runs took only when there is some", () => {
    const find = (s: Summary) => summaryStats(s).find((x) => x.label === "Time spent");
    expect(find(base)?.hint).toBeUndefined();
    expect(find({ ...base, fail_time: 20 })?.hint).toBe("20s on failures");
    expect(find(base)?.title).toContain("overhead and waits are not counted");
  });

  it("shows a cache that cost more than it saved as negative, in the danger tone", () => {
    const stat = summaryStats({ ...base, time_saved: 0, overhead: 5, net_saved: -5 })[1];
    expect(stat).toMatchObject({ value: "\u22125s", tone: "danger" });
  });

  it("links non-zero run and failure counts to their runs", () => {
    const hrefs = { runsHref: "#/activity", failuresHref: "#/activity?outcome=fail" };
    const stat = (stats: ReturnType<typeof summaryStats>, label: string) => stats.find((x) => x.label === label);
    const linked = summaryStats({ ...base, failures: 3 }, hrefs);
    expect(stat(linked, "Runs")?.href).toBe("#/activity");
    expect(stat(linked, "Failures")?.href).toBe("#/activity?outcome=fail");
    const empty = summaryStats({ ...base, runs: 0, failures: 0 }, hrefs);
    expect(stat(empty, "Runs")?.href).toBeUndefined();
    expect(stat(empty, "Failures")?.href).toBeUndefined();
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
      "No change",
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

  it("explains runs whose cost net saved leaves out, after the skips", () => {
    expect(summaryNote({ ...base, cost_unknown_runs: 1 })).toBe(
      "1 run came from an older gate-cache that did not record overhead or wait time, so net saved leaves out its cost.",
    );
    expect(summaryNote({ ...base, unknown_saved_skips: 1, cost_unknown_runs: 3 })).toBe(
      "1 skip had no recorded duration, so it adds nothing to time saved. " +
        "3 runs came from an older gate-cache that did not record overhead or wait time, so net saved leaves out their cost.",
    );
  });
});

describe("summaryStats sparklines", () => {
  const day = (over: Partial<DayBucket>): DayBucket => ({
    day: "2026-11-01",
    saved: 0,
    failures: 0,
    runs: 0,
    spent: 0,
    skips: 0,
    ran: 0,
    cost: 0,
    ...over,
  });
  const daily = [day({ saved: 60, cost: 10, spent: 30, runs: 4, skips: 2, ran: 4, failures: 1 }), day({ day: "2026-11-02" })];
  const spark = (label: string, stats = summaryStats(base, {}, daily)) =>
    stats.find((s) => s.label === label)?.spark;

  it("plots each day's value for the matching stat", () => {
    expect(spark("Time saved")?.values).toEqual([60, 0]);
    expect(spark("Net saved")?.values).toEqual([50, 0]);
    expect(spark("Time spent")?.values).toEqual([30, 0]);
    expect(spark("Runs")?.values).toEqual([4, 0]);
    expect(spark("Failures")?.values).toEqual([1, 0]);
    expect(spark("Time saved")?.color).toBe("--chart-saved");
    expect(spark("Failures")?.color).toBe("--chart-failures");
  });

  it("leaves a gap in the skip rate on a day where nothing checked the cache", () => {
    expect(spark("Skip rate")?.values).toEqual([0.5, null]);
  });

  it("draws no net saved sparkline when some runs in the plotted range did not record their cost", () => {
    expect(spark("Net saved", summaryStats({ ...base, cost_unknown_runs: 3 }, {}, daily))).toBeUndefined();
    // The picked days are clean, but the whole range the sparkline plots is not.
    const scoped = summaryStats(base, {}, daily, { costUnknownRuns: 2 });
    expect(spark("Net saved", scoped)).toBeUndefined();
  });

  it("draws no flaky gates sparkline, and none at all without daily data", () => {
    expect(spark("Flaky gates")).toBeUndefined();
    expect(summaryStats(base).every((s) => s.spark === undefined)).toBe(true);
  });
});

describe("pickedRange", () => {
  const days = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"].map((day) => ({
    day,
    saved: 0,
    failures: 0,
    runs: 0,
    spent: 0,
    skips: 0,
    ran: 0,
    cost: 0,
  }));

  it("returns the indexes of the scoped days within the whole range", () => {
    expect(pickedRange(days, days.slice(1, 3))).toEqual([1, 2]);
  });

  it("returns nothing until scoped days have loaded, or when they fall outside", () => {
    expect(pickedRange(days, undefined)).toBeUndefined();
    expect(pickedRange(days, [])).toBeUndefined();
    expect(pickedRange(days, [{ ...days[0]!, day: "2027-01-01" }])).toBeUndefined();
  });
});
