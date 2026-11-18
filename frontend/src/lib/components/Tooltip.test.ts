import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import Tooltip from "./Tooltip.svelte";

describe("Tooltip", () => {
  it("shows a plain explanation", () => {
    const { body } = render(Tooltip, { props: { text: "What this measures." } });
    expect(body).toContain("What this measures.");
    expect(body).not.toContain('class="title');
  });

  it("shows the title, a color bar and value per row, and the hint", () => {
    const { body } = render(Tooltip, {
      props: {
        title: "Tue, Nov 4",
        rows: [
          { color: "var(--chart-saved)", label: "Time saved", value: "12m 3s" },
          { color: "var(--chart-failures)", label: "Failures", value: "2" },
        ],
        hint: "Click to scope the page to this day",
      },
    });
    expect(body).toContain("Tue, Nov 4");
    expect(body.match(/class="bar[^"]*"/g)).toHaveLength(2);
    expect(body).toContain("background: var(--chart-saved)");
    expect(body).toMatch(/Time saved[\s\S]*?12m 3s/);
    expect(body).toContain("Click to scope the page to this day");
  });

  it("leaves out the hint line when there is none", () => {
    const { body } = render(Tooltip, { props: { title: "x", rows: [] } });
    expect(body).not.toContain('class="hint');
  });

  it("shows rows that share a label, such as a gate named Total", () => {
    const { body } = render(Tooltip, {
      props: {
        title: "Tue, Nov 4",
        rows: [
          { color: "var(--chart-series-1)", label: "Total", value: "1m" },
          { label: "Total", value: "2m" },
        ],
      },
    });
    expect(body.match(/class="row[^"]*"/g)).toHaveLength(2);
  });
});
