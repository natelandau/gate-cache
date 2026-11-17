import { describe, expect, it } from "vitest";
import type { EventRow } from "./api";
import { eventKeys, eventTitle, OUTCOMES, shortTree, timeText } from "./events";

function event(overrides: Partial<EventRow>): EventRow {
  return {
    ts: 1_794_268_800,
    repo: "/w/app/.git",
    repo_name: "app",
    name: "lint",
    outcome: "pass",
    duration: 54,
    saved: null,
    exit_code: 0,
    reason: null,
    tree: "0123456789abcdef0123",
    ...overrides,
  };
}

describe("OUTCOMES", () => {
  it("labels every outcome", () => {
    expect(Object.keys(OUTCOMES).sort()).toEqual(
      ["fail", "pass", "pass_unrecorded", "skip", "uncached"].sort(),
    );
    expect(OUTCOMES.fail.tone).toBe("danger");
    expect(OUTCOMES.skip.label).toBe("Skip");
  });
});

describe("timeText", () => {
  it("says saved for a skip and ran otherwise", () => {
    expect(timeText(event({ outcome: "skip", duration: null, saved: 91 }))).toBe("saved 1m 31s");
    expect(timeText(event({ outcome: "fail", duration: 54 }))).toBe("ran 54s");
  });

  it("marks an unknown time", () => {
    expect(timeText(event({ outcome: "skip", saved: null }))).toBe("saved, time unknown");
    expect(timeText(event({ outcome: "uncached", duration: null }))).toBe("ran, time unknown");
  });
});

describe("shortTree", () => {
  it("abbreviates a tree hash", () => {
    expect(shortTree("0123456789abcdef0123")).toBe("0123456789");
    expect(shortTree(null)).toBe("");
  });
});

describe("eventTitle", () => {
  it("lists the time, exit code, reason, and tree that apply", () => {
    const title = eventTitle(
      event({ outcome: "uncached", exit_code: 2, reason: "not a git repo", tree: null }),
    );
    expect(title).toContain("Uncached");
    expect(title).toContain("exit code 2");
    expect(title).toContain("not a git repo");
    expect(title).not.toContain("tree");
  });
});

describe("eventKeys", () => {
  it("is stable across an insert at the top and unique for identical events", () => {
    const a = event({ ts: 3, name: "lint" });
    const b = event({ ts: 2, name: "test" });
    const keys = eventKeys([a, b, b]);
    expect(new Set(keys).size).toBe(3);
    const after = eventKeys([event({ ts: 9 }), a, b, b]);
    expect(after.slice(1)).toEqual(keys);
  });
});
