import { describe, expect, it } from "vitest";
import type { BreakdownRow } from "./api";
import { breakdownBars, drillDown } from "./breakdown";
import { dimension, DIMENSIONS, isDimension } from "./dimensions";
import { href, parseHash } from "./router.svelte";

function row(label: string, overrides: Partial<BreakdownRow> = {}): BreakdownRow {
  return {
    key: JSON.stringify([label]),
    label,
    title: null,
    missing: false,
    repo: null,
    name: null,
    runs: 0,
    skip_rate: null,
    time_saved: 0,
    time_spent: 0,
    avg_run: null,
    median_run: null,
    failures: 0,
    gates: 1,
    ...overrides,
  };
}

const repos = [
  row("api", { repo: "/w/api/.git", title: "/w/api/.git", time_saved: 500, runs: 10, skip_rate: 0.5, failures: 1 }),
  row("web", { repo: "/w/web/.git", title: "/w/web/.git", time_saved: 90, runs: 40, skip_rate: 0.8, failures: 4 }),
  row("unknown repo", { missing: true, time_saved: 30, runs: 25, skip_rate: null, failures: 2 }),
];

const labels = (bars: ReturnType<typeof breakdownBars>) => bars.map((bar) => bar.label);

describe("breakdownBars", () => {
  it("sorts by each metric, with no skip rate as zero", () => {
    expect(labels(breakdownBars(repos, "saved", "repo", []))).toEqual(["api", "web", "unknown repo"]);
    expect(labels(breakdownBars(repos, "runs", "repo", []))).toEqual(["web", "unknown repo", "api"]);
    expect(labels(breakdownBars(repos, "fails", "repo", []))).toEqual(["web", "unknown repo", "api"]);
    const skip = breakdownBars(repos, "skip", "repo", []);
    expect(labels(skip)).toEqual(["web", "api", "unknown repo"]);
    expect(skip.at(-1)?.value).toBe(0);
  });

  it("sorts by time spent", () => {
    const spent = [row("a", { time_spent: 5 }), row("b", { time_spent: 50 })];
    expect(labels(breakdownBars(spent, "spent", "gate", []))).toEqual(["b", "a"]);
  });

  it("keys repo rows by the repo filter value and dims repos outside the filter", () => {
    const bars = breakdownBars(repos, "saved", "repo", ["-"]);
    expect(bars.map((bar) => [bar.key, bar.dimmed])).toEqual([
      ["/w/api/.git", true],
      ["/w/web/.git", true],
      ["-", false],
    ]);
    expect(bars[0]?.row).toBe(repos[0]);
    expect(breakdownBars(repos, "saved", "repo", []).some((bar) => bar.dimmed)).toBe(false);
  });

  it("keys other rows by their opaque key and never dims them", () => {
    const branches = [row("main"), row("No branch recorded", { key: '[null, null]', missing: true })];
    const bars = breakdownBars(branches, "saved", "branch", ["-"]);
    expect(bars.map((bar) => [bar.key, bar.dimmed])).toEqual([
      ['["main"]', false],
      ["[null, null]", false],
    ]);
  });

  it("passes the server's hover text through", () => {
    const bars = breakdownBars([row("main", { title: "x" }), row("dev")], "saved", "branch", []);
    expect(Object.fromEntries(bars.map((bar) => [bar.label, bar.title]))).toEqual({ main: "x", dev: undefined });
  });
});

describe("DIMENSIONS", () => {
  it("lists the dimensions the API accepts, Repo first, and recognizes only those", () => {
    expect(DIMENSIONS.map((d) => d.value)).toEqual(["repo", "gate", "source", "branch", "machine"]);
    expect(dimension("machine").label).toBe("Machine");
    expect(isDimension("branch")).toBe(true);
    expect(isDimension("tool")).toBe(false);
    expect(isDimension(null)).toBe(false);
  });
});

describe("drillDown", () => {
  it("filters to the repo for a repo row", () => {
    expect(drillDown("repo", repos[2]!)).toEqual({ kind: "repo", repo: "-" });
    expect(drillDown("repo", repos[0]!)).toEqual({ kind: "repo", repo: "/w/api/.git" });
  });

  it("opens the gate panel for a gate row", () => {
    const gate = row("lint · api", { repo: "/w/api/.git", name: "lint" });
    expect(drillDown("gate", gate)).toEqual({ kind: "gate", repo: "/w/api/.git", name: "lint" });
  });

  it("opens Activity on the row's runs, through a hash that round-trips", () => {
    const source = row("Agent: claude-code", { key: '["agent", "claude-code"]' });
    const action = drillDown("source", source);
    expect(action).toEqual({
      kind: "activity",
      route: {
        page: "activity",
        group: { by: "source", key: '["agent", "claude-code"]', label: "Source: Agent: claude-code" },
      },
    });
    if (action.kind !== "activity") throw new Error("expected an activity drill-down");
    expect(parseHash(href(action.route))).toEqual(action.route);
  });
});
