import { describe, expect, it } from "vitest";
import type { ActivityPage, EventRow } from "./api";
import { addPage, feedView } from "./activity";

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
