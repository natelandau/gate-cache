import { describe, expect, it } from "vitest";
import type { Summary } from "./api";
import type { DayBucket } from "./fill";
import { valueText } from "./format";
import { TERMS } from "./terms";
import { pickedRange, summaryNote, summaryStats } from "./summary";

const base: Summary = {
  time_saved: 90,
  time_spent: 60,
  fail_time: 0,
  unknown_saved_skips: 0,
  overhead: 0,
  waited: 0,
  cost_unknown_runs: 0,
  runs: 12,
  skips: 1,
  skip_rate: 0.5,
  uncached: 0,
  failures: 0,
  flaky_gates: 0,
  triage_items: 0,
  spot_checks: 0,
  spot_check_failures: 0,
  outcomes: { skip: 1, pass: 1, pass_unrecorded: 0, fail: 0, uncached: 0 },
  previous: null,
  daily: [],
};

const byLabel = (stats: ReturnType<typeof summaryStats>, label: string) => stats.find((x) => x.label === label);

describe("summaryStats", () => {
  it("lists the gates' own numbers, then the cache's", () => {
    const stats = summaryStats(base);
    expect(stats.map((s) => [s.label, valueText(s.value)])).toEqual([
      ["Gate calls", "12"],
      ["Time gates ran", "1m 0s"],
      [TERMS.saved.label, "1m 30s"],
      ["Gate failures", "0"],
      ["Flaky gates", "0"],
      [TERMS.spotChecks.label, `0 ${TERMS.spotChecks.ran}, 0 ${TERMS.spotChecks.failed}`],
      ["Cache skip rate", "50%"],
    ]);
    expect(byLabel(stats, "Gate calls")?.hint).toBe("11 ran · 1 skipped");
    expect(byLabel(stats, "Cache skip rate")?.hint).toBe("1 of 12 skipped");
  });

  it("defines every headline number in its info text", () => {
    expect(summaryStats(base).every((s) => (s.title ?? "").length > 0)).toBe(true);
  });

  it("flags problems and links flaky gates only when given a link", () => {
    const summary = { ...base, uncached: 2, failures: 3, flaky_gates: 1 };
    const linked = summaryStats(summary, { flakyHref: "#/triage?reason=flaky" });
    expect(byLabel(linked, "Cache skip rate")?.hint).toBe("1 of 10 skipped");
    expect(byLabel(linked, "Flaky gates")).toMatchObject({ tone: "flaky", href: "#/triage?reason=flaky" });
    expect(byLabel(linked, "Gate failures")).toMatchObject({ tone: "danger" });
    expect(byLabel(summaryStats(summary), "Flaky gates")?.href).toBeUndefined();
  });
});

describe("stat details", () => {
  it("hints at the time failed runs took only when there is some", () => {
    const find = (s: Summary) => byLabel(summaryStats(s), "Time gates ran");
    expect(find(base)?.hint).toBeUndefined();
    expect(find({ ...base, fail_time: 20 })?.hint).toBe("20s on failures");
    expect(find(base)?.title).toContain("Skipped calls take no time");
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

describe("spot check stat", () => {
  const hrefs = { spotChecksHref: "#/activity?spot_check=1" };
  const failedTone = (s: Summary) => {
    const value = byLabel(summaryStats(s, hrefs), TERMS.spotChecks.label)?.value;
    return typeof value === "string" ? undefined : value?.[1]?.tone;
  };

  it("shows the ran and failed counts, flagging failures only when some failed", () => {
    expect(failedTone({ ...base, spot_checks: 5, spot_check_failures: 2 })).toBe("danger");
    expect(failedTone({ ...base, spot_checks: 5 })).toBeUndefined();
  });
});

describe("summaryStats deltas", () => {
  it("leaves deltas off when there is no previous window", () => {
    expect(summaryStats(base).every((s) => s.delta === undefined)).toBe(true);
  });

  it("attaches a delta to every stat when there is a previous window", () => {
    const previous = { ...base, days: 30, runs: 6, spot_check_failures: 0 };
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
    spot_checks: 0,
    spot_check_failures: 0,
    ...over,
  });
  const daily = [
    day({ saved: 60, spent: 30, runs: 4, skips: 2, ran: 4, failures: 1, spot_checks: 3, spot_check_failures: 1 }),
    day({ day: "2026-11-02" }),
  ];
  const spark = (label: string, stats = summaryStats(base, {}, daily)) =>
    stats.find((s) => s.label === label)?.spark;

  it("plots each day's value for the matching stat", () => {
    expect(spark(TERMS.saved.label)).toEqual([{ values: [60, 0], color: "var(--chart-saved)" }]);
    expect(spark("Time gates ran")?.[0]?.values).toEqual([30, 0]);
    expect(spark("Gate calls")?.[0]?.values).toEqual([4, 0]);
    expect(spark("Gate failures")).toEqual([{ values: [1, 0], color: "var(--chart-failures)" }]);
  });

  it("plots spot checks and failed spot checks as two lines", () => {
    expect(spark(TERMS.spotChecks.label)).toEqual([
      { values: [3, 0], color: "var(--chart-runs)" },
      { values: [1, 0], color: "var(--chart-failures)" },
    ]);
  });

  it("leaves a gap in the skip rate on a day where nothing checked the cache", () => {
    expect(spark("Cache skip rate")?.[0]?.values).toEqual([0.5, null]);
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
    spot_checks: 0,
    spot_check_failures: 0,
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
