import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import StatStrip from "./StatStrip.svelte";

describe("StatStrip", () => {
  it("shows each delta with its tone and the comparison label", () => {
    const { body } = render(StatStrip, {
      props: {
        stats: [
          { label: "Runs", value: "12", delta: { text: "▲ 6%", tone: "good" } },
          { label: "Failures", value: "4", delta: { text: "▲ 12%", tone: "bad" } },
          { label: "Skip rate", value: "50%", delta: { text: "No change", tone: "neutral" } },
        ],
        deltaLabel: "vs prev 30d",
      },
    });
    expect(body).toMatch(/class="delta good[^"]*"[^>]*>[\s\S]*?lucide-trending-up[\s\S]*?Up[\s\S]*?6%/);
    expect(body).toMatch(/<span class="vs[^"]*">vs prev 30d<\/span>/);
    expect(body).toMatch(/class="delta bad[^"]*"[^>]*>[\s\S]*?lucide-trending-up[\s\S]*?12%/);
    expect(body).toMatch(/class="delta neutral[^"]*"[^>]*>(<!--[^>]*-->|\s)*No change/);
  });

  it("sets units in a muted span beside the digits", () => {
    const { body } = render(StatStrip, { props: { stats: [{ label: "Time saved", value: "6h 38m" }] } });
    expect(body).toMatch(/6(<!--[^>]*-->)*<span class="u[^"]*">h<\/span>/);
  });

  it("draws a sparkline for a stat that has one, and highlights picked days", () => {
    const { body } = render(StatStrip, {
      props: {
        stats: [{ label: "Runs", value: "4", spark: { values: [1, 2, 3], color: "--chart-runs" } }],
        highlight: [1, 1],
      },
    });
    expect(body).toMatch(/<svg[^>]*class="spark/);
    expect(body).toContain("var(--chart-runs)");
    expect(body).toMatch(/<g class="[^"]*\bdim\b/);
  });

  it("shows no delta line when a stat has none", () => {
    const { body } = render(StatStrip, {
      props: { stats: [{ label: "Runs", value: "12" }], deltaLabel: "vs prev 30d" },
    });
    expect(body).not.toContain("delta");
    expect(body).not.toContain("vs prev");
  });
});
