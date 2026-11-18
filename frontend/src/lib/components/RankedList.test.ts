import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import RankedList from "./RankedList.svelte";

describe("RankedList", () => {
  it("numbers each row and shows its title, subtitle, and value", () => {
    const { body } = render(RankedList, {
      props: {
        items: [
          { key: "a", title: "pytest", subtitle: "api-server", value: "1h 2m" },
          { key: "b", title: "ruff", subtitle: "app", value: "4", tone: "danger" },
        ],
      },
    });
    expect(body.match(/<li/g)).toHaveLength(2);
    expect(body).toMatch(/class="rank[^"]*"[^>]*>1</);
    expect(body).toMatch(/class="rank[^"]*"[^>]*>2</);
    expect(body).toContain("api-server");
    expect(body).toMatch(/class="value[^"]*"[^>]*>1h 2m</);
    expect(body).toMatch(/class="value[^"]*\bdanger\b[^"]*"[^>]*>4</);
  });

  it("draws an inline bar for each row's share of the largest", () => {
    const { body } = render(RankedList, {
      props: {
        items: [
          { key: "a", title: "e2e", subtitle: "api", value: "2h", share: 1, barColor: "var(--chart-saved)" },
          { key: "b", title: "lint", subtitle: "api", value: "1h", share: 0.5, barColor: "var(--chart-saved)" },
        ],
      },
    });
    expect(body).toMatch(/class="fill[^"]*"[^>]*style="width: 50%; background: var\(--chart-saved\)/);
  });

  it("cuts a long title with its full text as a title attribute", () => {
    const long = "a-gate-name-long-enough-to-overflow-the-ranked-list-column";
    const { body } = render(RankedList, {
      props: { items: [{ key: "a", title: long, subtitle: "api", value: "1" }] },
    });
    expect(body).toMatch(new RegExp(`class="title[^"]*" title="${long}"`));
  });

  it("makes a row a button only when it has a select handler", () => {
    const { body } = render(RankedList, {
      props: {
        items: [
          { key: "a", title: "pytest", subtitle: "app", value: "1", onselect: () => {} },
          { key: "b", title: "ruff", subtitle: "app", value: "2" },
        ],
      },
    });
    expect(body.match(/<button/g)).toHaveLength(1);
  });
});
