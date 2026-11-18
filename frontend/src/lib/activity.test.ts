import { describe, expect, it } from "vitest";
import type { ActivityPage, EventRow } from "./api";
import { activityHint, activitySubject, addPage, feedView, filterParts } from "./activity";
import type { RangeSpec } from "./range";

function ev(ts: number): EventRow {
  return {
    ts,
    repo: null,
    repo_name: "unknown repo",
    name: "lint",
    outcome: "pass",
    duration: 1,
    saved: null,
    exit_code: 0,
    reason: null,
    tree: null,
    reported: false,
  };
}

const first: ActivityPage = { events: [ev(30), ev(20)], next_before: "20:2" };
const A = '["/a/.git","7d"]';
const B = '[null,"30d"]';
const second: ActivityPage = { events: [ev(10)], next_before: null };

describe("feedView", () => {
  it("shows the live first page while nothing more is loaded", () => {
    expect(feedView(first, null, A)).toEqual({ events: first.events, next: "20:2", newer: false });
    expect(feedView(undefined, null, A)).toEqual({ events: [], next: null, newer: false });
  });

  it("keeps the loaded pages and flags newer live events", () => {
    const paged = addPage(null, first, second, A);
    expect(feedView(first, paged, A)).toEqual({
      events: [ev(30), ev(20), ev(10)],
      next: null,
      newer: false,
    });
    const live: ActivityPage = { events: [ev(40), ev(30)], next_before: "30:3" };
    expect(feedView(live, paged, A).newer).toBe(true);
    expect(feedView(live, paged, A).events.map((e) => e.ts)).toEqual([30, 20, 10]);
  });

  it("flags newer events when the frozen first page was empty", () => {
    const paged = addPage(null, { events: [], next_before: null }, { events: [], next_before: null }, A);
    expect(feedView({ events: [ev(1)], next_before: null }, paged, A).newer).toBe(true);
  });
});

describe("addPage", () => {
  it("appends each further page and follows its cursor", () => {
    const one = addPage(null, first, { events: [ev(15)], next_before: "15:1" }, A);
    const two = addPage(one, { events: [ev(99)], next_before: null }, second, A);
    expect(two.first).toBe(first);
    expect(two.rest.map((e) => e.ts)).toEqual([15, 10]);
    expect(two.next).toBeNull();
  });

  it("starts over from the live page when the inputs changed", () => {
    const one = addPage(null, first, { events: [ev(15)], next_before: "15:1" }, A);
    const fresh: ActivityPage = { events: [ev(50)], next_before: "50:1" };
    const two = addPage(one, fresh, second, B);
    expect(two.first).toBe(fresh);
    expect(two.rest.map((e) => e.ts)).toEqual([10]);
    expect(two.inputs).toBe(B);
  });
});

describe("feedView inputs", () => {
  it("ignores pages loaded for other inputs", () => {
    const paged = addPage(null, first, second, A);
    const live: ActivityPage = { events: [ev(5)], next_before: null };
    expect(feedView(live, paged, B)).toEqual({ events: [ev(5)], next: null, newer: false });
  });
});

describe("activitySubject", () => {
  it("names the active outcome and reason", () => {
    expect(activitySubject({})).toBe("gate calls");
    expect(activitySubject({ outcome: "fail" })).toBe('"Ran and failed" gate calls');
    expect(activitySubject({ reason: "x y" })).toBe('gate calls with reason "x y"');
    expect(activitySubject({ outcome: "uncached", reason: "x y" })).toBe(
      '"Ran with cache off" gate calls with reason "x y"',
    );
    expect(activitySubject({ outcome: "fail", group: { by: "branch", key: "[]", label: "Branch: main" } })).toBe(
      '"Ran and failed" gate calls in "Branch: main"',
    );
  });

  it("names the day, hour, gate, and flaky filters", () => {
    // Days are named by the empty-state title in place of the range, not by the subject.
    expect(activitySubject({ span: { from: "2026-11-03", to: "2026-11-03" } })).toBe("gate calls");
    expect(activitySubject({ slot: { weekday: 2, hour: 9 } })).toBe("gate calls on Tuesdays 09:00 to 10:00");
    expect(activitySubject({ outcome: "fail", gate: { repo: null, name: "lint" }, flaky: true })).toBe(
      '"Ran and failed" gate calls of lint on flaky trees',
    );
  });
});

describe("activityHint", () => {
  const range: RangeSpec = { kind: "preset", preset: "30d" };
  const all: RangeSpec = { kind: "preset", preset: "all" };
  const scope = { range, repoLabel: null, recording: true };

  it("falls back to the generic hint without page filters", () => {
    expect(activityHint({}, scope)).toBe("Run a gate through gate-cache, or pick a longer range.");
  });

  it("asks to turn recording on first", () => {
    expect(activityHint({ outcome: "fail" }, { ...scope, recording: false })).toBe(
      "Turn recording on with gate-cache stats on, then run a gate through gate-cache.",
    );
  });

  it("names the filter to clear", () => {
    expect(activityHint({ outcome: "fail" }, scope)).toBe(
      "Pick All outcomes, or pick a longer range.",
    );
    expect(activityHint({ reason: "x" }, scope)).toBe(
      "Remove the reason filter, or pick a longer range.",
    );
    expect(activityHint({ outcome: "uncached", reason: "x" }, scope)).toBe(
      "Pick All outcomes and remove the reason filter, or pick a longer range.",
    );
    expect(activityHint({ group: { by: "source", key: "[]", label: "Source: CI" } }, scope)).toBe(
      'Remove the "Source: CI" filter, or pick a longer range.',
    );
  });

  it("names every page filter to remove", () => {
    expect(activityHint({ flaky: true }, scope)).toBe(
      "Remove the flaky filter, or pick a longer range.",
    );
    expect(
      activityHint({ outcome: "fail", span: { from: "2026-11-03", to: "2026-11-03" }, slot: { weekday: 1, hour: 2 } }, scope),
    ).toBe("Pick All outcomes and remove the day and hour filters, or pick a longer range.");
    expect(
      activityHint({ reason: "x", gate: { repo: null, name: "a" }, flaky: true }, scope),
    ).toBe("Remove the reason, gate, and flaky filters, or pick a longer range.");
  });

  it("drops the range advice for all time", () => {
    expect(activityHint({ reason: "x" }, { ...scope, range: all })).toBe(
      "Remove the reason filter.",
    );
  });
});

describe("filterParts", () => {
  it("lists each removable filter with its chip text and the filter left without it", () => {
    const filter = { outcome: "fail" as const, reason: "x", gate: { repo: "/a/.git", name: "lint" }, flaky: true as const };
    const parts = filterParts(filter);
    expect(parts.map((p) => p.label)).toEqual(["Reason: x", "Gate: lint", "Flaky trees only"]);
    expect(parts[1]?.title).toBe("lint in /a/.git");
    expect(parts[2]?.without).toEqual({ outcome: "fail", reason: "x", gate: { repo: "/a/.git", name: "lint" } });
    expect(filterParts({ outcome: "fail" })).toEqual([]);
  });
});
