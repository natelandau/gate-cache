import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import FilterChip from "./FilterChip.svelte";

describe("FilterChip", () => {
  it("shows the label with its full text as a title and a labeled remove button", () => {
    const { body } = render(FilterChip, {
      props: { label: "Reason: dirty tree", title: "dirty tree", removeLabel: "Remove reason filter", onremove: () => {} },
    });
    expect(body).toContain("Reason: dirty tree");
    expect(body).toContain('title="dirty tree"');
    expect(body).toMatch(/<button[^>]*aria-label="Remove reason filter"/);
  });

  it("draws the remove button as an x icon", () => {
    const { body } = render(FilterChip, {
      props: { label: "Days: Nov 3", removeLabel: "Show the whole range", onremove: () => {} },
    });
    expect(body).toMatch(/<button[^>]*>[\s\S]*<svg[^>]*lucide-x/);
  });
});
