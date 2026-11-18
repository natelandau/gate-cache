import { createRawSnippet } from "svelte";
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import PageHeader from "./PageHeader.svelte";

describe("PageHeader", () => {
  it("shows the title, the subtitle, and the page's chips", () => {
    const children = createRawSnippet(() => ({ render: () => "<span>Days: Nov 3</span>" }));
    const { body } = render(PageHeader, {
      props: { title: "Overview", headingId: "overview-title", subtitle: "All repos · Last 30 days", children },
    });
    expect(body).toMatch(/<h1 id="overview-title"[^>]*>Overview<\/h1>/);
    expect(body).toContain("All repos · Last 30 days");
    expect(body).toContain("Days: Nov 3");
  });

  it("leaves out the subtitle when there is none", () => {
    const { body } = render(PageHeader, { props: { title: "Gates", headingId: "gates-title" } });
    expect(body).not.toContain("subtitle");
  });
});
