import { describe, expect, it } from "vitest";
import {
  dotStyle,
  gapLabels,
  gapThreshold,
  labelSlots,
  MAX_DOTS,
  rollingMedian,
  trendChange,
  trendLayout,
} from "./trend";

const HOUR = 3600;
const DAY = 86400;

/** Passes `spacing` seconds apart starting at `start`, with durations from `durations`. */
function passes(durations: number[], spacing: number, start = 0) {
  return durations.map((duration, i) => ({ ts: start + i * spacing, duration }));
}

describe("gapThreshold", () => {
  it.each([
    { name: "never less than a day for frequent runs", spacing: 5 * 60, expected: DAY },
    { name: "four times the usual spacing for daily runs", spacing: DAY, expected: 4 * DAY },
    { name: "a day for a single pass", spacing: 0, expected: DAY },
  ])("is $name", ({ spacing, expected }) => {
    const trend = spacing ? passes([1, 1, 1, 1], spacing) : passes([1], 0);
    expect(gapThreshold(trend)).toBe(expected);
  });
});

describe("rollingMedian", () => {
  it("gives no trend for fewer values than the window", () => {
    expect(rollingMedian([1, 2, 3, 4])).toEqual([null, null, null, null]);
  });

  it("takes the median of real neighbors only, shrinking at the ends", () => {
    expect(rollingMedian([10, 1, 5, 9, 2, 8])).toEqual([10, 5, 5, 5, 8, 8]);
  });
});

describe("trendLayout", () => {
  const steady = passes([3, 4, 5, 4, 3, 4], HOUR);
  const later = passes([6, 7], HOUR, steady.at(-1)!.ts + 9 * DAY);

  it("keeps runs a few hours apart in one stretch with no gap", () => {
    const layout = trendLayout(steady);
    expect(layout.gaps).toEqual([]);
    expect(layout.marks.map((m) => m.slot)).toEqual([0, 1, 2, 3, 4, 5]);
    expect(layout.slots).toBe(6);
  });

  it("breaks the stretch at a long idle time and gives the break its own slot", () => {
    const layout = trendLayout([...steady, ...later]);
    expect(layout.segments.map((s) => s.length)).toEqual([6, 2]);
    expect(layout.gaps).toEqual([{ from: 5, to: 7, seconds: 9 * DAY }]);
  });

  it("draws a trend only through stretches long enough for the window", () => {
    const layout = trendLayout([...steady, ...later]);
    expect(layout.segments[0]!.every((m) => m.rolling !== null)).toBe(true);
    expect(layout.segments[1]!.every((m) => m.rolling === null)).toBe(true);
  });

  it("buckets passes past the dot limit, within stretches, keeping every pass counted", () => {
    const busy = passes(Array.from({ length: 1200 }, (_, i) => 10 + (i % 7)), 60);
    const idleThenBusy = passes([20, 21, 22], 60, busy.at(-1)!.ts + 5 * DAY);
    const layout = trendLayout([...busy, ...idleThenBusy]);
    expect(layout.bucketed).toBe(true);
    expect(layout.marks.length).toBeLessThanOrEqual(MAX_DOTS);
    expect(layout.marks.reduce((sum, m) => sum + m.count, 0)).toBe(1203);
    expect(layout.gaps).toHaveLength(1);
    const first = layout.marks[0]!;
    expect(first.min).toBe(10);
    expect(first.max).toBe(12);
    expect(first.endTs).toBeGreaterThan(first.ts);
  });

  it("keeps the dot limit when many short stretches each end in a partial bucket", () => {
    const bursts = Array.from({ length: 200 }, (_, b) => passes([1, 2, 3, 4, 5], 60, b * 10 * DAY)).flat();
    const layout = trendLayout(bursts);
    expect(layout.marks.length).toBeLessThanOrEqual(MAX_DOTS);
    expect(layout.marks.reduce((sum, m) => sum + m.count, 0)).toBe(1000);
  });

  it("draws one dot per pass up to the limit", () => {
    const layout = trendLayout(passes(Array.from({ length: MAX_DOTS }, () => 1), 60));
    expect(layout.bucketed).toBe(false);
    expect(layout.marks).toHaveLength(MAX_DOTS);
  });
});

describe("trendChange", () => {
  it("compares the last five passes with the first five", () => {
    const result = trendChange(passes([10, 10, 10, 10, 10, 12, 12, 12, 12, 12], HOUR))!;
    expect(result.window).toBe(5);
    expect(result.change).toBeCloseTo(0.2);
  });

  it("widens the windows to a tenth of the passes, so one outlier moves nothing", () => {
    const durations = Array.from({ length: 200 }, () => 10);
    durations[199] = 100;
    expect(trendChange(passes(durations, HOUR))).toEqual({ change: 0, window: 20 });
  });

  it("has no change when the two windows would overlap", () => {
    expect(trendChange(passes([1, 2, 3, 4, 5, 6, 7, 8, 9], HOUR))).toBeNull();
  });
});

describe("dotStyle", () => {
  it("shrinks and fades dots as the count rises", () => {
    const counts = [10, 100, 400].map(dotStyle);
    for (let i = 1; i < counts.length; i++) {
      expect(counts[i]!.r).toBeLessThan(counts[i - 1]!.r);
      expect(counts[i]!.opacity).toBeLessThan(counts[i - 1]!.opacity);
    }
  });
});

describe("labelSlots", () => {
  it("labels the first run after every gap, and never two labels too close", () => {
    const a = passes([1, 1, 1, 1, 1, 1, 1, 1, 1, 1], HOUR);
    const b = passes([1, 1, 1, 1, 1, 1, 1, 1, 1, 1], HOUR, 20 * DAY);
    const layout = trendLayout([...a, ...b]);
    const slots = labelSlots(layout, 600, String, 64);
    expect(slots).toContain(0);
    expect(slots).toContain(layout.segments[1]![0]!.slot);
    const px = slots.map((s) => ((s + 0.5) / layout.slots) * 600);
    for (let i = 1; i < px.length; i++) expect(px[i]! - px[i - 1]!).toBeGreaterThanOrEqual(64);
  });

  it("labels nothing before the plot has a width", () => {
    expect(labelSlots(trendLayout(passes([1, 2, 3, 4, 5], HOUR)), 0, String)).toEqual([]);
  });

  it("drops a label that repeats the text of one already kept", () => {
    const layout = trendLayout(passes(Array.from({ length: 40 }, () => 1), HOUR));
    expect(labelSlots(layout, 2000, () => "Nov 3")).toEqual([0]);
  });
});

describe("gapLabels", () => {
  it("drops a gap label that would overlap the one before it", () => {
    const stretches = [0, 1, 2, 3].map((k) => passes([1, 1, 1, 1, 1], HOUR, k * 10 * DAY));
    const layout = trendLayout(stretches.flat());
    expect(gapLabels(layout, 2000)).toHaveLength(3);
    expect(gapLabels(layout, 50)).toHaveLength(1);
  });
});
