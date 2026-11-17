import { describe, expect, it } from "vitest";
import { emptyHint, emptyTitle } from "./scope";

describe("emptyTitle", () => {
  it("names the range and the repo", () => {
    expect(emptyTitle("runs", { range: "7d", repoLabel: "api-server" })).toBe(
      "No runs in the last 7 days for api-server.",
    );
  });

  it("names only the range without a repo", () => {
    expect(emptyTitle("flaky gates", { range: "24h", repoLabel: null })).toBe(
      "No flaky gates in the last 24 hours.",
    );
  });

  it("reads naturally for all time", () => {
    expect(emptyTitle("runs", { range: "all", repoLabel: null })).toBe("No runs recorded yet.");
    expect(emptyTitle("runs", { range: "all", repoLabel: "app" })).toBe("No runs recorded for app.");
  });
});

describe("emptyHint", () => {
  it("asks to turn recording on first", () => {
    expect(emptyHint({ range: "7d", repoLabel: "app", recording: false })).toBe(
      "Turn recording on with gate-cache stats on, then run a gate through gate-cache.",
    );
  });

  it("suggests clearing the repo filter when one is set", () => {
    expect(emptyHint({ range: "7d", repoLabel: "app", recording: true })).toBe(
      "Pick All repos or a longer range.",
    );
  });

  it("suggests a longer range without a repo filter", () => {
    expect(emptyHint({ range: "7d", repoLabel: null, recording: true })).toBe(
      "Run a gate through gate-cache, or pick a longer range.",
    );
    expect(emptyHint({ range: "all", repoLabel: null, recording: null })).toBe(
      "Run a gate through gate-cache.",
    );
  });
});
