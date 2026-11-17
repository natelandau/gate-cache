import { createRawSnippet } from "svelte";
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import Module from "./Module.svelte";

const children = createRawSnippet(() => ({ render: () => "<p>module body</p>" }));
const base = { title: "Activity", titleId: "activity-title", emptyTitle: "No runs", children };

describe("Module", () => {
  it("labels the section with its title", () => {
    const { body } = render(Module, { props: { ...base, loading: false, empty: false } });
    expect(body).toMatch(/<section[^>]*aria-labelledby="activity-title"/);
    expect(body).toMatch(/<h2[^>]*id="activity-title"[^>]*>Activity<\/h2>/);
    expect(body).toContain("module body");
  });

  it("shows loading text instead of the content", () => {
    const { body } = render(Module, { props: { ...base, loading: true, empty: false } });
    expect(body).toContain("Loading activity");
    expect(body).not.toContain("module body");
  });

  it("shows the empty state when there is nothing to show", () => {
    const { body } = render(Module, {
      props: { ...base, loading: false, empty: true, emptyDetail: "Widen the range" },
    });
    expect(body).toContain("No runs");
    expect(body).toContain("Widen the range");
    expect(body).not.toContain("module body");
  });

  it("shows an error notice and no empty state when the load failed", () => {
    const { body } = render(Module, {
      props: { ...base, loading: false, empty: true, error: new Error("boom") },
    });
    expect(body).toContain('role="alert"');
    expect(body).toContain("boom");
    expect(body).not.toContain("No runs");
  });

  it("keeps the content beside an error from a reload", () => {
    const { body } = render(Module, {
      props: { ...base, loading: false, empty: false, error: new Error("boom") },
    });
    expect(body).toContain("boom");
    expect(body).toContain("module body");
  });

  it("uses the noun for the loading and error text", () => {
    const { body } = render(Module, {
      props: { ...base, noun: "GitHub activity", loading: true, empty: false, error: new Error("x") },
    });
    expect(body).toContain("Loading GitHub activity");
    expect(body).toContain("Could not load GitHub activity");
  });
});
