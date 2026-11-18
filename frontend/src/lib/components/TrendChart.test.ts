import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import TrendChart from "./TrendChart.svelte";

const trend = (n: number) => Array.from({ length: n }, (_, i) => ({ ts: 1_700_000_000 + i * 3600, duration: 4 + i }));

describe("TrendChart", () => {
  it("lists a handful of passes, newest first, instead of plotting them", () => {
    const { body } = render(TrendChart, { props: { trend: trend(3) } });
    expect(body).not.toMatch(/class="plot\b/);
    const items = [...body.matchAll(/class="took[^"]*">([^<]+)</g)].map((m) => m[1]);
    expect(items).toEqual(["6s", "5s", "4s"]);
  });

  it("plots five passes and more", () => {
    const { body } = render(TrendChart, { props: { trend: trend(5) } });
    expect(body).toMatch(/class="plot\b/);
    expect(body).not.toMatch(/class="passes\b/);
  });
});
