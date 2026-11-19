import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import CalendarHeatmap from "./CalendarHeatmap.svelte";

// 2026-11-03 is a Tuesday, so the first week has two padding cells.
const days = [
  { day: "2026-11-03", saved: 0, failures: 0, runs: 0, spent: 0, skips: 0, ran: 0, spot_checks: 0, spot_check_failures: 0 },
  { day: "2026-11-04", saved: 60, failures: 1, runs: 2, spent: 0, skips: 0, ran: 0, spot_checks: 0, spot_check_failures: 0 },
  { day: "2026-11-05", saved: 120, failures: 0, runs: 10, spent: 0, skips: 0, ran: 0, spot_checks: 0, spot_check_failures: 0 },
];

function cellStyles(body: string): string[] {
  return [...body.matchAll(/class="cell[^"]*"[^>]*style="background: ([^;"]+)/g)].map((m) => m[1] ?? "");
}

describe("CalendarHeatmap", () => {
  it("colors each day on the metric's ramp and leaves padding blank", () => {
    const { body } = render(CalendarHeatmap, { props: { days, metric: "runs" } });
    expect(cellStyles(body)).toEqual([
      "var(--heat-empty)",
      "var(--heat-runs-1)",
      "var(--heat-runs-5)",
    ]);
    // A month grid starts on Monday, so a Tuesday start pads one cell and a Thursday end three.
    expect(body.match(/class="cell pad[ "]/g)?.length).toBe(1 + 3);
  });

  it("lays out a short range as Monday-first week rows with week labels", () => {
    const { body } = render(CalendarHeatmap, { props: { days, metric: "runs" } });
    expect(body).toMatch(/class="calendar layout-month/);
    expect(body.match(/class="week-label[^"]*"/g)).toHaveLength(1);
  });

  it("lays out a long range as week columns", () => {
    const long = Array.from({ length: 60 }, (_, i) => {
      const d = new Date(Date.UTC(2026, 8, 1 + i));
      return { day: d.toISOString().slice(0, 10), saved: 0, failures: 0, runs: i % 3, spent: 0, skips: 0, ran: 0, spot_checks: 0, spot_check_failures: 0 };
    });
    const { body } = render(CalendarHeatmap, { props: { days: long, metric: "runs" } });
    expect(body).toMatch(/class="calendar layout-weeks/);
  });

  it("labels each week, the weekdays, and each cell", () => {
    const { body } = render(CalendarHeatmap, { props: { days, metric: "runs" } });
    const weekStart = new Date(2026, 10, 3).toLocaleString(undefined, { month: "short", day: "numeric" });
    expect(body).toContain(`>${weekStart}<`);
    const monday = new Date(1970, 0, 5).toLocaleString(undefined, { weekday: "short" }).slice(0, 1);
    expect(body).toMatch(new RegExp(`class="weekday[^"]*"[^>]*>${monday}<`));
    expect(body).toMatch(/title="[^"]*Gate calls: 10"/);
  });

  it("lists active days in a screen-reader table", () => {
    const { body } = render(CalendarHeatmap, { props: { days, metric: "fail" } });
    expect(body).toMatch(/<table[\s\S]*<th scope="col">Failures<\/th>/);
    expect(body.match(/<th scope="row">/g)?.length).toBe(1);
  });

  it("shows the legend from empty to the top step", () => {
    const { body } = render(CalendarHeatmap, { props: { days, metric: "saved" } });
    expect(body).toContain("Less");
    expect(body).toContain("More");
    expect(body).toContain("var(--heat-saved-5)");
  });

  it("stays static without a select handler", () => {
    const { body } = render(CalendarHeatmap, { props: { days, metric: "runs" } });
    expect(body).not.toContain("<button");
  });

  it("makes each day a toggle with one tab stop when it can select", () => {
    const { body } = render(CalendarHeatmap, {
      props: { days, metric: "runs", selected: { from: "2026-11-04", to: "2026-11-04" }, onselect: () => {} },
    });
    expect(body.match(/<button/g)?.length).toBe(3);
    expect(body.match(/tabindex="0"/g)?.length).toBe(1);
    expect(body.match(/aria-pressed="true"/g)?.length).toBe(1);
    expect(body).toMatch(/<button[^>]*class="cell[^"]*selected[^"]*"[^>]*aria-pressed="true"|aria-pressed="true"[^>]*class="cell[^"]*selected/);
    expect(body.match(/class="cell[^"]*dimmed/g)?.length).toBe(2);
    expect(body).toMatch(/aria-label="[^"]*Gate calls: 2[^"]*"/);
  });
});
