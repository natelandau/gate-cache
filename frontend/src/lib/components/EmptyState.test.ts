import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import EmptyState from "./EmptyState.svelte";

describe("EmptyState", () => {
  it("shows an icon tile, the title, and the detail", () => {
    const { body } = render(EmptyState, {
      props: { title: "No runs in this range", detail: "Pick a longer range.", icon: "hourglass" },
    });
    expect(body).toMatch(/class="tile[^"]*"[^>]*>(<!--[^>]*-->)*<svg/);
    expect(body).toMatch(/<p class="title[^"]*">No runs in this range<\/p>/);
    expect(body).toContain("Pick a longer range.");
  });

  it("uses the inbox icon by default", () => {
    const { body } = render(EmptyState, { props: { title: "Nothing here" } });
    expect(body).toContain("lucide-inbox");
  });
});
