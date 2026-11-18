import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { Summary } from "../lib/api";
import type { Query } from "../lib/query.svelte";
import type { SummaryView } from "../lib/summary";
import Overview from "./Overview.svelte";

const summary: Summary = {
  time_saved: 118,
  time_spent: 60,
  fail_time: 0,
  unknown_saved_skips: 0,
  overhead: 0,
  waited: 0,
  net_saved: 118,
  cost_unknown_runs: 0,
  runs: 12,
  skips: 6,
  skip_rate: 0.5,
  uncached: 0,
  failures: 0,
  flaky_gates: 0,
  outcomes: { skip: 6, pass: 6, pass_unrecorded: 0, fail: 0, uncached: 0 },
  previous: {
    time_saved: 100,
    time_spent: 60,
    net_saved: 100,
    runs: 12,
    skips: 6,
    skip_rate: 0.5,
    failures: 0,
    flaky_gates: 0,
    days: 30,
  },
  daily: [],
};

function query(data: SummaryView | undefined, loading = false): Query<SummaryView> {
  return { data, error: undefined, loading } as unknown as Query<SummaryView>;
}

const days = [{ day: "2026-11-17", saved: 118, failures: 0, runs: 12, spent: 0, skips: 0, ran: 0, cost: 0 }];

describe("Overview", () => {
  it("shows the stat strip with deltas, the activity calendar, and the daily chart", () => {
    const { body } = render(Overview, {
      props: { query: query({ summary, days }), repoLabel: null },
    });
    expect(body).toMatch(/lucide-trending-up[\s\S]*?18%/);
    expect(body).toContain("vs prev 30d");
    expect(body).toMatch(/<h2[^>]*id="calendar-title"[^>]*>Activity<\/h2>/);
    expect(body).toMatch(/<h2[^>]*id="daily-title"[^>]*>Daily<\/h2>/);
  });

  it("shows the hourly, top gates, outcome mix, and flaky modules", () => {
    const { body } = render(Overview, {
      props: { query: query({ summary, days }), repoLabel: null },
    });
    expect(body).toMatch(/<h2[^>]*id="hourly-title"[^>]*>When gates run<\/h2>/);
    expect(body).toMatch(/<h2[^>]*id="top-gates-title"[^>]*>Top gates<\/h2>/);
    expect(body).toMatch(/<h2[^>]*id="outcome-title"[^>]*>Outcome mix<\/h2>/);
    expect(body).toMatch(/<h2[^>]*id="flaky-gates-title"[^>]*>Flaky gates<\/h2>/);
    expect(body).toMatch(/Skip<\/span>(?:\s|<!--[^>]*-->)*<(?:span|a)[^>]*>6<\/(?:span|a)>(?:\s|<!--[^>]*-->)*<span[^>]*>50%</);
  });

  it("shows the reasons, recent failures, slowdowns, and breakdown modules", () => {
    const { body } = render(Overview, {
      props: { query: query({ summary, days }), repoLabel: null },
    });
    expect(body).toMatch(/<h2[^>]*id="reasons-title"[^>]*>Why gates ran uncached<\/h2>/);
    expect(body).toMatch(/<h2[^>]*id="failures-title"[^>]*>Recent failures<\/h2>/);
    expect(body).toMatch(/<h2[^>]*id="slowdowns-title"[^>]*>Gates getting slower<\/h2>/);
    expect(body).toMatch(/<h2[^>]*id="breakdown-title"[^>]*>Breakdown<\/h2>/);
    expect(body).toMatch(/<select[^>]*>[\s\S]*Repo[\s\S]*Gate[\s\S]*Source[\s\S]*Branch[\s\S]*Machine/);
    expect(body).toContain("All repos, click a name to filter");
  });

  it("hides deltas when there is no previous window", () => {
    const { body } = render(Overview, {
      props: { query: query({ summary: { ...summary, previous: null }, days }), repoLabel: null },
    });
    expect(body).not.toContain("vs prev");
  });

  it("shows each module's empty state when nothing ran", () => {
    const outcomes = { skip: 0, pass: 0, pass_unrecorded: 0, fail: 0, uncached: 0 };
    const empty = { ...summary, runs: 0, outcomes, previous: null };
    const { body } = render(Overview, {
      props: { query: query({ summary: empty, days }), repoLabel: "api-server" },
    });
    expect(body.match(/for api-server\./g)).toHaveLength(3);
  });

  it("links run sets to Activity and makes the charts pickable", () => {
    const { body } = render(Overview, {
      props: { query: query({ summary, days }), repoLabel: null },
    });
    expect(body).toContain('href="#/activity"');
    expect(body).toContain('href="#/activity?outcome=skip"');
    expect(body).toMatch(/aria-pressed="false"/);
    expect(body).toMatch(/role="listbox"/);
    expect(body).not.toContain("Show the whole range");
  });

  it("shows a chip for picked days and marks them on the calendar", () => {
    const { body } = render(Overview, {
      props: { query: query({ summary, days }), repoLabel: null, span: { from: "2026-11-17", to: "2026-11-17" } },
    });
    expect(body).toContain("Days: Nov 17");
    expect(body).toContain('aria-label="Show the whole range"');
    expect(body).toMatch(/aria-pressed="true"/);
    // The scoped modules load their own data, so the shell summary's stats are not shown.
    expect(body).not.toContain("vs prev 30d");
  });
});
