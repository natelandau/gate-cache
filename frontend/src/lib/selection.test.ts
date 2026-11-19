import { describe, expect, it } from "vitest";
import {
  rangeDays,
  spanFromInputs,
  clampScope,
  cursorKey,
  dayCursor,
  inSpan,
  isDay,
  selectedRange,
  spanAt,
  spanRange,
  spanLabel,
  spanOf,
  toggleDay,
  type Cursor,
} from "./selection";

const seconds = (y: number, m: number, d: number) => new Date(y, m - 1, d).getTime() / 1000;

describe("spanOf", () => {
  it("orders the two days", () => {
    expect(spanOf("2026-11-05", "2026-11-03")).toEqual({ from: "2026-11-03", to: "2026-11-05" });
    expect(spanOf("2026-11-03", "2026-11-03")).toEqual({ from: "2026-11-03", to: "2026-11-03" });
  });
});

describe("toggleDay", () => {
  it("selects, replaces, and clears a single day", () => {
    const day = toggleDay(undefined, "2026-11-03");
    expect(day).toEqual({ from: "2026-11-03", to: "2026-11-03" });
    expect(toggleDay(day, "2026-11-04")).toEqual({ from: "2026-11-04", to: "2026-11-04" });
    expect(toggleDay(day, "2026-11-03")).toBeUndefined();
  });

  it("narrows a range to the clicked day instead of clearing it", () => {
    expect(toggleDay({ from: "2026-11-03", to: "2026-11-05" }, "2026-11-03")).toEqual({
      from: "2026-11-03",
      to: "2026-11-03",
    });
  });
});

describe("inSpan", () => {
  it("includes both ends", () => {
    const span = { from: "2026-11-03", to: "2026-11-05" };
    expect(inSpan(span, "2026-11-03")).toBe(true);
    expect(inSpan(span, "2026-11-05")).toBe(true);
    expect(inSpan(span, "2026-11-06")).toBe(false);
    expect(inSpan(undefined, "2026-11-03")).toBe(false);
  });
});

describe("spanLabel", () => {
  it("names one day, a range, and a range across years", () => {
    expect(spanLabel({ from: "2026-11-03", to: "2026-11-03" })).toBe("Nov 3");
    expect(spanLabel({ from: "2026-11-03", to: "2026-11-05" })).toBe("Nov 3 to Nov 5");
    expect(spanLabel({ from: "2025-12-30", to: "2026-01-02" })).toBe("Dec 30, 2025 to Jan 2, 2026");
  });
});

describe("clampScope", () => {
  const scope = { repos: ["a"], from: seconds(2026, 11, 1), to: seconds(2026, 11, 10), tz: "UTC" };
  const later = seconds(2027, 1, 1);

  it("returns the scope unchanged without a span", () => {
    expect(clampScope(scope, undefined, later)).toEqual(scope);
  });

  it("narrows to a span inside the range, from local midnight to the midnight after", () => {
    expect(clampScope(scope, { from: "2026-11-03", to: "2026-11-04" }, later)).toEqual({
      ...scope,
      from: seconds(2026, 11, 3),
      to: seconds(2026, 11, 5),
    });
  });

  it("covers a 25-hour day at the end of daylight saving time", () => {
    const open = { repos: [], tz: "UTC" };
    const { from = 0, to = 0 } = clampScope(open, { from: "2026-11-01", to: "2026-11-01" }, later);
    expect(to - from).toBe(25 * 3600);
  });

  it("keeps the overlap of a span that sticks out of the range", () => {
    expect(clampScope(scope, { from: "2026-10-30", to: "2026-11-03" }, later)).toEqual({
      ...scope,
      from: seconds(2026, 11, 1),
      to: seconds(2026, 11, 4),
    });
  });

  it("gives an empty window for a span outside the range", () => {
    const clamped = clampScope(scope, { from: "2026-12-01", to: "2026-12-02" }, later);
    expect(clamped.from).toBe(clamped.to);
  });

  it("ends at now, so today compares like a rolling preset", () => {
    const now = seconds(2026, 11, 3) + 3600;
    expect(clampScope({ repos: [], tz: "UTC" }, { from: "2026-11-03", to: "2026-11-03" }, now).to).toBe(now);
  });
});

describe("isDay", () => {
  it("accepts only real calendar dates", () => {
    expect(isDay("2026-11-03")).toBe(true);
    expect(isDay("2026-13-01")).toBe(false);
    expect(isDay("2026-02-30")).toBe(false);
    expect(isDay("x")).toBe(false);
  });
});

describe("cursorKey", () => {
  const steps = { ArrowLeft: -1, ArrowRight: 1 };
  const at = (n: number, anchor: number | null = null): Cursor => ({ at: n, anchor });
  const key = (k: string, shiftKey = false) => ({ key: k, shiftKey });

  it("moves the cursor and clamps it at the ends", () => {
    expect(cursorKey(at(2), key("ArrowRight"), steps, 5, null)).toEqual({ cursor: at(3) });
    expect(cursorKey(at(4), key("ArrowRight"), steps, 5, null)).toEqual({ cursor: at(4) });
    expect(cursorKey(at(0), key("ArrowLeft"), steps, 5, null)).toEqual({ cursor: at(0) });
    expect(cursorKey(at(2), key("Home"), steps, 5, null)).toEqual({ cursor: at(0) });
    expect(cursorKey(at(2), key("End"), steps, 5, null)).toEqual({ cursor: at(4) });
  });

  it("extends the selection from the anchor with Shift", () => {
    expect(cursorKey(at(2), key("ArrowRight", true), steps, 5, null)).toEqual({
      cursor: at(3, 2),
      select: [2, 3],
    });
    expect(cursorKey(at(3, 2), key("ArrowLeft", true), steps, 5, [2, 3])).toEqual({
      cursor: at(2, 2),
      select: [2, 2],
    });
    expect(cursorKey(at(2, 2), key("ArrowLeft", true), steps, 5, [2, 2])).toEqual({
      cursor: at(1, 2),
      select: [1, 2],
    });
  });

  it("toggles the cursor day with Enter or Space", () => {
    expect(cursorKey(at(1), key("Enter"), steps, 5, null)).toEqual({ cursor: at(1, 1), select: [1, 1] });
    expect(cursorKey(at(1), key(" "), steps, 5, null)).toEqual({ cursor: at(1, 1), select: [1, 1] });
    expect(cursorKey(at(1, 1), key("Enter"), steps, 5, [1, 1])).toEqual({ cursor: at(1), select: null });
  });

  it("clears with Escape", () => {
    expect(cursorKey(at(1, 0), key("Escape"), steps, 5, [0, 1])).toEqual({ cursor: at(1), select: null });
  });

  it("ignores other keys and an empty list", () => {
    expect(cursorKey(at(1), key("a"), steps, 5, null)).toBeNull();
    expect(cursorKey(at(0), key("ArrowRight"), steps, 0, null)).toBeNull();
  });
});

describe("selectedRange", () => {
  const days = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"].map((day) => ({ day }));

  it("returns the first and last index inside the span", () => {
    expect(selectedRange(days, { from: "2026-11-04", to: "2026-11-05" })).toEqual([1, 2]);
    expect(selectedRange(days, { from: "2026-11-01", to: "2026-11-03" })).toEqual([0, 0]);
  });

  it("returns null without a span or when no day is in it", () => {
    expect(selectedRange(days)).toBeNull();
    expect(selectedRange(days, { from: "2026-12-01", to: "2026-12-02" })).toBeNull();
  });
});

describe("spanRange", () => {
  it("describes the span as a custom range for empty-state copy", () => {
    const range = { kind: "preset", preset: "30d" } as const;
    expect(spanRange(range)).toBe(range);
    expect(spanRange(range, { from: "2026-11-03", to: "2026-11-04" })).toEqual({
      kind: "custom",
      start: "2026-11-03",
      end: "2026-11-04",
    });
  });
});

describe("dayCursor", () => {
  const days = (...list: string[]) => list.map((day) => ({ day }));

  it("finds the cursor and anchor by day, so a longer list keeps them on the same days", () => {
    expect(dayCursor(days("2026-11-03", "2026-11-04"), "2026-11-03", "2026-11-04", [1, 1])).toEqual({ at: 0, anchor: 1 });
    expect(dayCursor(days("2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"), "2026-11-03", "2026-11-04", [3, 3])).toEqual({
      at: 2,
      anchor: 3,
    });
  });

  it("falls back to the first picked day, then the last day", () => {
    expect(dayCursor(days("2026-11-03", "2026-11-04", "2026-11-05"), null, null, [1, 1])).toEqual({ at: 1, anchor: null });
    expect(dayCursor(days("2026-11-03", "2026-11-04", "2026-11-05"), "2026-10-01", null, null)).toEqual({ at: 2, anchor: null });
  });

  it("drops the anchor when nothing is picked or its day is gone", () => {
    expect(dayCursor(days("2026-11-03", "2026-11-04"), "2026-11-03", "2026-11-04", null)).toEqual({ at: 0, anchor: null });
    expect(dayCursor(days("2026-11-03", "2026-11-04"), "2026-11-03", "2026-10-01", [1, 1])).toEqual({ at: 0, anchor: null });
  });
});

describe("spanAt", () => {
  const days = ["2026-11-03", "2026-11-04", "2026-11-05"].map((day) => ({ day }));

  it("returns the days at two positions, or undefined to clear", () => {
    expect(spanAt(days, [0, 2])).toEqual({ from: "2026-11-03", to: "2026-11-05" });
    expect(spanAt(days, null)).toBeUndefined();
    expect(spanAt(days, [0, 9])).toBeUndefined();
  });
});

describe("spanFromInputs", () => {
  it.each([
    ["2025-03-02", "2025-03-04", undefined, undefined, { from: "2025-03-02", to: "2025-03-04" }],
    ["2025-03-02", "", undefined, undefined, { from: "2025-03-02", to: "2025-03-02" }],
    ["", "2025-03-04", undefined, undefined, undefined],
    ["2025-03-05", "2025-03-04", undefined, undefined, undefined],
    ["2025-03-01", "2025-03-04", "2025-03-02", undefined, undefined],
    ["2025-03-02", "2025-03-09", "2025-03-02", "2025-03-08", undefined],
  ])("%s to %s within %s..%s", (from, to, min, max, expected) => {
    expect(spanFromInputs(from, to, min, max)).toEqual(expected);
  });
});

describe("rangeDays", () => {
  const now = new Date(2025, 2, 10, 15, 0);

  it("ends a custom range on its last day, not the day after", () => {
    expect(rangeDays({ kind: "custom", start: "2025-03-02", end: "2025-03-04" }, now)).toEqual({
      min: "2025-03-02",
      max: "2025-03-04",
    });
  });

  it("ends at today for a range that reaches now, with no start for all time", () => {
    expect(rangeDays({ kind: "preset", preset: "all" }, now)).toEqual({ min: undefined, max: "2025-03-10" });
  });
});
