import { describe, expect, it } from "vitest";
import type { Preset, RangeSpec } from "./range";
import { emptyHint, emptyTitle } from "./scope";

const preset = (value: Preset): RangeSpec => ({ kind: "preset", preset: value });

describe("emptyTitle", () => {
  it("names the range and the repo", () => {
    expect(emptyTitle("runs", { range: preset("7d"), repoLabel: "api-server" })).toBe(
      "No runs in the last 7 days for api-server.",
    );
  });

  it("names only the range without a repo", () => {
    expect(emptyTitle("flaky gates", { range: preset("24h"), repoLabel: null })).toBe(
      "No flaky gates in the last 24 hours.",
    );
    expect(emptyTitle("runs", { range: preset("1y"), repoLabel: null })).toBe("No runs in the last 12 months.");
  });

  it("reads naturally for all time", () => {
    expect(emptyTitle("runs", { range: preset("all"), repoLabel: null })).toBe("No runs recorded yet.");
    expect(emptyTitle("runs", { range: preset("all"), repoLabel: "app" })).toBe("No runs recorded for app.");
  });

  it("reads naturally for calendar periods and custom dates", () => {
    expect(emptyTitle("runs", { range: { kind: "period", period: "this_month" }, repoLabel: null })).toBe(
      "No runs this month.",
    );
    expect(emptyTitle("runs", { range: { kind: "period", period: "today" }, repoLabel: "3 repos" })).toBe(
      "No runs today for 3 repos.",
    );
    expect(
      emptyTitle("runs", { range: { kind: "custom", start: "2026-10-01", end: "2026-11-17" }, repoLabel: null }),
    ).toBe("No runs from Oct 1 to Nov 17.");
    expect(
      emptyTitle("runs", { range: { kind: "custom", start: "2026-11-17", end: "2026-11-17" }, repoLabel: null }),
    ).toBe("No runs on Nov 17.");
  });
});

describe("emptyTitle with picked days", () => {
  it("names the days in place of the range", () => {
    expect(
      emptyTitle("runs", { range: preset("7d"), repoLabel: "app", span: { from: "2026-11-03", to: "2026-11-03" } }),
    ).toBe("No runs on Nov 3 for app.");
  });
});

describe("emptyHint", () => {
  it("asks to turn recording on first", () => {
    expect(emptyHint({ range: preset("7d"), repoLabel: "app", recording: false })).toBe(
      "Turn recording on with gate-cache stats on, then run a gate through gate-cache.",
    );
  });

  it("suggests other days when days are picked", () => {
    expect(emptyHint({ range: preset("7d"), repoLabel: "app", recording: true, span: { from: "2026-11-03", to: "2026-11-03" } })).toBe(
      "Pick other days, or remove the day filter.",
    );
    expect(emptyHint({ range: preset("7d"), repoLabel: null, recording: false, span: { from: "2026-11-03", to: "2026-11-03" } })).toBe(
      "Turn recording on with gate-cache stats on, then run a gate through gate-cache.",
    );
  });

  it("suggests clearing the repo filter when one is set", () => {
    expect(emptyHint({ range: preset("7d"), repoLabel: "app", recording: true })).toBe(
      "Pick All repos or a longer range.",
    );
  });

  it("suggests a longer range without a repo filter", () => {
    expect(emptyHint({ range: preset("7d"), repoLabel: null, recording: true })).toBe(
      "Run a gate through gate-cache, or pick a longer range.",
    );
    expect(emptyHint({ range: { kind: "period", period: "yesterday" }, repoLabel: null, recording: true })).toBe(
      "Run a gate through gate-cache, or pick a longer range.",
    );
    expect(emptyHint({ range: preset("all"), repoLabel: null, recording: null })).toBe(
      "Run a gate through gate-cache.",
    );
  });
});
