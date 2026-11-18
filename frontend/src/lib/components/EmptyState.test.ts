import { describe, expect, it } from "vitest";
import { html } from "../render.test-utils";
import EmptyState from "./EmptyState.svelte";

describe("EmptyState", () => {
  it("shows an icon tile, the title, and the detail", () => {
    const body = html(EmptyState, {
      props: { title: "No runs in this range", detail: "Pick a longer range." },
    });
    expect(body).toMatch(/class="tile[^"]*"[^>]*><svg/);
    expect(body).toMatch(/<p class="title[^"]*">No runs in this range<\/p>/);
    expect(body).toContain("Pick a longer range.");
  });

  it("shows the inbox icon", () => {
    const body = html(EmptyState, { props: { title: "Nothing here" } });
    expect(body).toContain("lucide-inbox");
  });
});
