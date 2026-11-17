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
    expect(body).toMatch(/class="value accent[^"]*"[^>]*>1h 2m</);
    expect(body).toMatch(/class="value danger[^"]*"[^>]*>4</);
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
