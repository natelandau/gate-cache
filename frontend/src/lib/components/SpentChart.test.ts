import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import { spentRows, spentSeries } from "../spent";
import SpentChart from "./SpentChart.svelte";

const body = {
  status: "all" as const,
  gates: [{ repo: "/r", repo_name: "r", name: "test", label: "test", total: 90 }],
  daily: [
    { day: "2026-11-03", gates: [0], other: 0 },
    { day: "2026-11-04", gates: [60], other: 30 },
  ],
};
const series = spentSeries(body);
const rows = spentRows(body.daily, series);

describe("SpentChart", () => {
  it("makes gate legend entries buttons and leaves Other as text", () => {
    const { body: html } = render(SpentChart, { props: { rows, series, onpickgate: () => {} } });
    expect(html.match(/<button[^>]*class="entry/g)?.length).toBe(1);
    expect(html).toMatch(/<span[^>]*class="entry[^"]*"[^>]*>.*Other/s);
  });

  it("names each day as an option with its total when pickable", () => {
    const { body: html } = render(SpentChart, {
      props: { rows, series, selected: { from: "2026-11-04", to: "2026-11-04" }, onselect: () => {} },
    });
    expect(html.match(/role="option"/g)?.length).toBe(2);
    expect(html.match(/aria-selected="true"/g)?.length).toBe(1);
    expect(html).toMatch(/aria-label="[^"]*1m 30s spent"/);
  });

  it("has no picking layer without a select handler", () => {
    const { body: html } = render(SpentChart, { props: { rows, series } });
    expect(html).not.toContain('class="picker');
  });
});
