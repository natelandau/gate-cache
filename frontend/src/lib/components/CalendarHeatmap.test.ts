import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import CalendarHeatmap from "./CalendarHeatmap.svelte";

// 2026-11-03 is a Tuesday, so the first week has two padding cells.
const days = [
  { day: "2026-11-03", saved: 0, failures: 0, runs: 0, spent: 0, skips: 0, ran: 0, cost: 0 },
  { day: "2026-11-04", saved: 60, failures: 1, runs: 2, spent: 0, skips: 0, ran: 0, cost: 0 },
  { day: "2026-11-05", saved: 120, failures: 0, runs: 10, spent: 0, skips: 0, ran: 0, cost: 0 },
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
    expect(body.match(/class="cell pad[ "]/g)?.length).toBe(2 + 2);
  });

  it("labels the month, the weekdays, and each cell", () => {
    const { body } = render(CalendarHeatmap, { props: { days, metric: "runs" } });
    const month = new Date(2026, 10, 1).toLocaleString(undefined, { month: "short" });
    expect(body).toContain(`>${month}<`);
    const monday = new Date(1970, 0, 5).toLocaleString(undefined, { weekday: "short" });
    expect(body).toContain(`>${monday}<`);
    expect(body).toMatch(/title="[^"]*Runs: 10"/);
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
    expect(body).toMatch(/aria-label="[^"]*Runs: 2[^"]*"/);
  });
});
