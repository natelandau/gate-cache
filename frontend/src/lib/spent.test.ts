import { describe, expect, it } from "vitest";
import type { Spent } from "./api";
import { OTHER_COLOR, SPENT_COLORS, emptySpentDay, seriesColor, spentRows, spentSeries, spentTotals } from "./spent";

const gate = (name: string, total: number) => ({
  repo: "/r",
  repo_name: "r",
  name,
  label: name,
  total,
});

function body(other: number[]): Spent {
  return {
    status: "all",
    gates: [gate("test", 5), gate("lint", 3)],
    daily: other.map((o, i) => ({ day: `2026-11-0${i + 1}`, gates: [3, 2], other: o })),
  };
}

describe("spentSeries", () => {
  it("lists one series per gate, in order, with no Other when every day has none", () => {
    const series = spentSeries(body([0, 0]));
    expect(series.map((s) => s.key)).toEqual(["0", "1"]);
    expect(series.map((s) => s.label)).toEqual(["test", "lint"]);
    expect(series.map((s) => s.color)).toEqual(SPENT_COLORS.slice(0, 2));
    expect(series[0]?.gate?.name).toBe("test");
  });

  it("adds Other last when any day has time outside the top gates", () => {
    const series = spentSeries(body([0, 1]));
    expect(series.at(-1)).toEqual({ key: "other", label: "Other", color: OTHER_COLOR, gate: null });
    expect(series).toHaveLength(3);
  });
});

describe("gates beyond the palette", () => {
  const six: Spent = {
    status: "all",
    gates: ["a", "b", "c", "d", "e", "f"].map((n, i) => gate(n, 10 - i)),
    daily: [{ day: "2026-11-01", gates: [6, 5, 4, 3, 2, 1], other: 0 }],
  };

  it("limits series to the palette and adds Other for the dropped gate", () => {
    const series = spentSeries(six);
    expect(series.map((s) => s.color)).toEqual([...SPENT_COLORS, OTHER_COLOR]);
    expect(series.at(-1)?.key).toBe("other");
  });

  it("counts a dropped gate's seconds as Other", () => {
    const [row] = spentRows(six.daily, spentSeries(six));
    expect(row?.total).toBe(21);
    expect(row?.segments.at(-1)).toEqual({ key: "other", start: 20, end: 21 });
  });
});

describe("spentRows", () => {
  it("stacks each day bottom-up in series order", () => {
    const b = body([1]);
    const rows = spentRows(b.daily, spentSeries(b));
    expect(rows).toEqual([
      {
        day: "2026-11-01",
        total: 6,
        segments: [
          { key: "0", start: 0, end: 3 },
          { key: "1", start: 3, end: 5 },
          { key: "other", start: 5, end: 6 },
        ],
      },
    ]);
  });
});

describe("emptySpentDay", () => {
  it("returns a zero day with one slot per gate", () => {
    expect(emptySpentDay(2)("2026-01-01")).toEqual({ day: "2026-01-01", gates: [0, 0], other: 0 });
  });
});

describe("seriesColor", () => {
  it("gives each ranked gate its own hue and Other the neutral gray", () => {
    expect(seriesColor(0)).toBe("var(--chart-series-1)");
    expect(seriesColor(4)).toBe("var(--chart-series-5)");
    expect(seriesColor(5)).toBe("var(--chart-neutral)");
  });
});

describe("spentTotals", () => {
  it("sums each series over the range and the grand total", () => {
    const body = {
      status: "all" as const,
      gates: [
        { repo: "/a", repo_name: "api", name: "e2e", label: "e2e · api", total: 70 },
        { repo: "/b", repo_name: "web", name: "test", label: "test · web", total: 20 },
      ],
      daily: [
        { day: "2026-11-03", gates: [30, 10], other: 5 },
        { day: "2026-11-04", gates: [40, 10], other: 0 },
      ],
    };
    const series = spentSeries(body);
    const { items, total } = spentTotals(series, spentRows(body.daily, series));
    expect(items.map((i) => [i.name, i.repo, i.total])).toEqual([
      ["e2e", "api", 70],
      ["test", "web", 20],
      ["Other", "", 5],
    ]);
    expect(total).toBe(95);
  });
});
