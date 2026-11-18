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

const byLabel = (stats: ReturnType<typeof summaryStats>, label: string) => stats.find((x) => x.label === label);

describe("summaryStats", () => {
  it("lists the gates' own numbers first and what the cache saved last", () => {
    const stats = summaryStats(base);
    expect(stats.map((s) => [s.label, s.value])).toEqual([
      ["Gate calls", "12"],
      ["Time gates ran", "1m 0s"],
      ["Gate failures", "0"],
      ["Flaky gates", "0"],
      ["Cache skip rate", "50%"],
      ["Time saved by cache", "1m 30s"],
      ["Net saved by cache", "1m 30s"],
    ]);
    expect(byLabel(stats, "Gate calls")?.hint).toBe("11 ran · 1 skipped");
    expect(byLabel(stats, "Cache skip rate")?.hint).toBe("1 of 12 skipped");
  });

  it("defines every headline number in its info text", () => {
    expect(summaryStats(base).every((s) => (s.title ?? "").length > 0)).toBe(true);
  });

  it("flags problems and links flaky gates only when given a link", () => {
    const summary = { ...base, uncached: 2, failures: 3, flaky_gates: 1 };
    const linked = summaryStats(summary, { flakyHref: "#/flaky" });
    expect(byLabel(linked, "Cache skip rate")?.hint).toBe("1 of 10 skipped");
    expect(byLabel(linked, "Flaky gates")).toMatchObject({ tone: "flaky", href: "#/flaky" });
    expect(byLabel(linked, "Gate failures")).toMatchObject({ tone: "danger" });
    expect(byLabel(summaryStats(summary), "Flaky gates")?.href).toBeUndefined();
  });
});

describe("net saved", () => {
  it("names what it subtracts and explains the sum in its title", () => {
    const stat = byLabel(summaryStats({ ...base, overhead: 3, waited: 60, net_saved: 27 }), "Net saved by cache");
    expect(stat).toMatchObject({ value: "27s", hint: "after 1m 3s of cache cost", tone: "default" });
    expect(stat?.title).toContain("Time saved minus");
  });

  it("hints at the time failed runs took only when there is some", () => {
    const find = (s: Summary) => byLabel(summaryStats(s), "Time gates ran");
    expect(find(base)?.hint).toBeUndefined();
    expect(find({ ...base, fail_time: 20 })?.hint).toBe("20s on failures");
    expect(find(base)?.title).toContain("Skipped calls take no time");
  });

  it("shows a cache that cost more than it saved as negative, in the danger tone", () => {
    const stat = byLabel(summaryStats({ ...base, time_saved: 0, overhead: 5, net_saved: -5 }), "Net saved by cache");
    expect(stat).toMatchObject({ value: "\u22125s", tone: "danger" });
  });

  it("links non-zero call and failure counts to their runs", () => {
    const hrefs = { runsHref: "#/activity", failuresHref: "#/activity?outcome=fail" };
    const linked = summaryStats({ ...base, failures: 3 }, hrefs);
    expect(byLabel(linked, "Gate calls")?.href).toBe("#/activity");
    expect(byLabel(linked, "Gate failures")?.href).toBe("#/activity?outcome=fail");
    const empty = summaryStats({ ...base, runs: 0, failures: 0 }, hrefs);
    expect(byLabel(empty, "Gate calls")?.href).toBeUndefined();
    expect(byLabel(empty, "Gate failures")?.href).toBeUndefined();
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
      "100%",
      "No change",
      "No change",
      "No change",
      "No change",
      "No change",
      "No change",
    ]);
    expect(byLabel(stats, "Gate calls")?.delta?.dir).toBe("up");
  });
});

describe("summaryNote", () => {
  it("explains skips without a duration", () => {
    expect(summaryNote(base)).toBeUndefined();
    expect(summaryNote({ ...base, unknown_saved_skips: 1 })).toBe(
      "1 skipped call had no recorded duration, so it adds nothing to time saved by cache.",
    );
    expect(summaryNote({ ...base, unknown_saved_skips: 2 })).toBe(
      "2 skipped calls had no recorded duration, so they add nothing to time saved by cache.",
    );
  });

  it("explains calls whose cost net saved leaves out, after the skips", () => {
    expect(summaryNote({ ...base, cost_unknown_runs: 1 })).toBe(
      "1 call came from an older gate-cache that did not record overhead or wait time, so net saved by cache leaves out its cost.",
    );
    expect(summaryNote({ ...base, unknown_saved_skips: 1, cost_unknown_runs: 3 })).toBe(
      "1 skipped call had no recorded duration, so it adds nothing to time saved by cache. " +
        "3 calls came from an older gate-cache that did not record overhead or wait time, so net saved by cache leaves out their cost.",
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
    expect(spark("Time saved by cache")?.values).toEqual([60, 0]);
    expect(spark("Net saved by cache")?.values).toEqual([50, 0]);
    expect(spark("Time gates ran")?.values).toEqual([30, 0]);
    expect(spark("Gate calls")?.values).toEqual([4, 0]);
    expect(spark("Gate failures")?.values).toEqual([1, 0]);
    expect(spark("Time saved by cache")?.color).toBe("var(--chart-saved)");
    expect(spark("Gate failures")?.color).toBe("var(--chart-failures)");
  });

  it("leaves a gap in the skip rate on a day where nothing checked the cache", () => {
    expect(spark("Cache skip rate")?.values).toEqual([0.5, null]);
  });

  it("draws no net saved sparkline when some runs in the plotted range did not record their cost", () => {
    expect(spark("Net saved by cache", summaryStats({ ...base, cost_unknown_runs: 3 }, {}, daily))).toBeUndefined();
    // The picked days are clean, but the whole range the sparkline plots is not.
    const scoped = summaryStats(base, { costUnknownRuns: 2 }, daily);
    expect(spark("Net saved by cache", scoped)).toBeUndefined();
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
