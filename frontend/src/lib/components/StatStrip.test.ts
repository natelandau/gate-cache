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
    expect(body).toMatch(/class="delta good[^"]*"[^>]*>\s*▲ 6%/);
    expect(body).toMatch(/<span class="vs[^"]*">vs prev 30d<\/span>/);
    expect(body).toMatch(/class="delta bad[^"]*"[^>]*>\s*▲ 12%/);
    expect(body).toMatch(/class="delta neutral[^"]*"[^>]*>\s*No change/);
  });

  it("shows no delta line when a stat has none", () => {
    const { body } = render(StatStrip, {
      props: { stats: [{ label: "Runs", value: "12" }], deltaLabel: "vs prev 30d" },
    });
    expect(body).not.toContain("delta");
    expect(body).not.toContain("vs prev");
  });
});
