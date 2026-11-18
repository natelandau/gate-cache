import { describe, expect, it } from "vitest";
import { html } from "../render.test-utils";
import Sidebar from "./Sidebar.svelte";

describe("Sidebar", () => {
  it("shows an icon beside each page", () => {
    const body = html(Sidebar, { props: { current: "overview", flakyCount: null } });
    const links = [...body.matchAll(/<a [\s\S]*?<\/a>/g)].map((m) => m[0]);
    expect(links).toHaveLength(4);
    for (const link of links) expect(link).toContain("<svg");
    expect(links[0]).toContain('aria-current="page"');
  });

  it("shows the flaky count as a flaky badge", () => {
    const body = html(Sidebar, { props: { current: "gates", flakyCount: 2 } });
    expect(body).toMatch(/class="badge flaky[^"]*"[^>]*>2</);
  });

  it("shows no badge when nothing is flaky", () => {
    const body = html(Sidebar, { props: { current: "gates", flakyCount: 0 } });
    expect(body).not.toContain("badge");
  });
});
