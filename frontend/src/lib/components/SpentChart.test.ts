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
    expect(html).toMatch(/aria-label="[^"]*1m 30s of run time"/);
  });

  it("lists each gate with its total beside the chart, then the grand total", () => {
    const { body: html } = render(SpentChart, { props: { rows, series } });
    expect(html).toMatch(/class="entry[\s\S]*?test[\s\S]*?1m 0s/);
    expect(html).toMatch(/class="grand[^"]*"[\s\S]*?Total[\s\S]*?1m 30s/);
  });

  it("uses the gate series colors and draws no stroke between segments", () => {
    const { body: html } = render(SpentChart, { props: { rows, series } });
    expect(html).not.toContain("--chart-runs-");
    expect(html).toContain("var(--chart-series-1)");
  });

  it("cuts a long gate name with its full text as a title", () => {
    const long = "a-gate-name-long-enough-to-overflow-the-legend-column-of-the-chart";
    const wide = spentSeries({ ...body, gates: [{ ...body.gates[0]!, name: long, label: long }] });
    const { body: html } = render(SpentChart, { props: { rows: spentRows(body.daily, wide), series: wide } });
    expect(html).toContain(`title="${long}`);
  });

  it("has no picking layer without a select handler", () => {
    const { body: html } = render(SpentChart, { props: { rows, series } });
    expect(html).not.toContain('class="picker');
  });
});
