import { describe, expect, it } from "vitest";
import { html } from "../render.test-utils";
import DailyChart from "./DailyChart.svelte";

const days = [
  { day: "2026-11-03", saved: 0, failures: 0, runs: 0, spent: 0, skips: 0, ran: 0, cost: 0 },
  { day: "2026-11-04", saved: 60, failures: 1, runs: 2, spent: 0, skips: 0, ran: 0, cost: 0 },
  { day: "2026-11-05", saved: 120, failures: 0, runs: 10, spent: 0, skips: 0, ran: 0, cost: 0 },
];

describe("DailyChart", () => {
  it("leads with the range's gate calls and failures, then time saved by cache", () => {
    const body = html(DailyChart, { props: { days } });
    expect(body).toMatch(/class="headline[^"]*"[\s\S]*?12[\s\S]*?gate calls/);
    expect(body).toMatch(/class="headline[^"]*"[\s\S]*?3<span class="u[^"]*">m<\/span>[\s\S]*?saved by cache/);
    expect(body).toMatch(/class="fails[^"]*"[^>]*>1</);
  });

  it("names the two series in a legend instead of over the axis", () => {
    const body = html(DailyChart, { props: { days } });
    expect(body).toMatch(/class="legend[\s\S]*?Gate calls[\s\S]*?Failures/);
    expect(body).not.toContain("panel-label");
  });

  it("has no picking layer without a select handler", () => {
    const body = html(DailyChart, { props: { days } });
    expect(body).not.toContain('class="picker');
  });

  it("marks picked days with a ring and dims the rest", () => {
    const body = html(DailyChart, {
      props: { days, selected: { from: "2026-11-04", to: "2026-11-05" }, onselect: () => {} },
    });
    expect(body).toMatch(/role="listbox"/);
    expect(body).toMatch(/tabindex="0"/);
    expect(body.match(/class="column[^"]*selected/g)?.length).toBe(2);
    expect(body.match(/class="column[^"]*dimmed/g)?.length).toBe(1);
  });

  it("names each day as an option with its values and picked state", () => {
    const body = html(DailyChart, {
      props: { days, selected: { from: "2026-11-04", to: "2026-11-04" }, onselect: () => {} },
    });
    expect(body.match(/role="option"/g)?.length).toBe(3);
    expect(body.match(/aria-selected="true"/g)?.length).toBe(1);
    expect(body).toMatch(/aria-label="[^"]*2 gate calls, 1 failure, 1m 0s saved by cache"/);
  });
});
