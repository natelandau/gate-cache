import { describe, expect, it } from "vitest";
import type { Coalescing } from "./api";
import { coalescingNote, waitEndings, waitFacts } from "./coalescing";

const base: Coalescing = {
  runs: 40,
  unknown_runs: 0,
  waited: 4,
  skipped: 2,
  reported: 1,
  ran: 1,
  timed_out: 0,
  total_wait: 916,
  median_wait: 7,
  saved: 90,
};

describe("waitEndings", () => {
  it("lists every ending in order, skips blue and reported failures red", () => {
    expect(waitEndings(base).map((e) => [e.key, e.count, e.color])).toEqual([
      ["skipped", 2, "var(--chart-skip)"],
      ["reported", 1, "var(--chart-fail)"],
      ["ran", 1, "var(--chart-neutral)"],
    ]);
  });
});

describe("waitFacts", () => {
  it("shows the count with its share of runs, then the wait totals", () => {
    expect(waitFacts(base).map((f) => [f.label, f.value])).toEqual([
      ["Calls that waited", "4 (10%)"],
      ["Total wait", "15m 16s"],
      ["Typical wait", "7s"],
      ["Saved by skips after a wait", "1m 30s"],
    ]);
  });

  it("reads n/a for a share or a median it cannot compute", () => {
    const facts = waitFacts({ ...base, runs: 0, waited: 0, median_wait: null });
    expect(facts[0]?.value).toBe("0 (n/a)");
    expect(facts[2]?.value).toBe("n/a");
  });
});

describe("coalescingNote", () => {
  it("is empty when nothing is left out", () => {
    expect(coalescingNote(base)).toBeUndefined();
  });

  it("names waits that timed out and runs from an older gate-cache", () => {
    expect(coalescingNote({ ...base, timed_out: 1, unknown_runs: 1 })).toBe(
      "1 wait reached the timeout. 1 call in this range came from an older gate-cache that did not record waits, so it is not counted here.",
    );
    expect(coalescingNote({ ...base, unknown_runs: 5 })).toBe(
      "5 calls in this range came from an older gate-cache that did not record waits, so they are not counted here.",
    );
  });
});
