import { describe, expect, it } from "vitest";
import { html } from "../render.test-utils";
import Sidebar from "./Sidebar.svelte";

describe("Sidebar", () => {
  it("shows an icon beside each page", () => {
    const body = html(Sidebar, { props: { current: "overview", triageCount: null } });
    const links = [...body.matchAll(/<a [\s\S]*?<\/a>/g)].map((m) => m[0]);
    expect(links).toHaveLength(4);
    for (const link of links) expect(link).toContain("<svg");
    expect(links[0]).toContain('aria-current="page"');
  });

  it("shows the triage count as a badge on Triage", () => {
    const body = html(Sidebar, { props: { current: "gates", triageCount: 2 } });
    expect(body).toMatch(/href="#\/triage"[\s\S]*?class="badge[^"]*"[^>]*>2</);
  });

  it("shows no badge when nothing needs triage", () => {
    const body = html(Sidebar, { props: { current: "gates", triageCount: 0 } });
    expect(body).not.toContain("badge");
  });
});
