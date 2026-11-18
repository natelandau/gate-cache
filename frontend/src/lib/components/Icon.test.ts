import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import Icon from "./Icon.svelte";

describe("Icon", () => {
  it("hides a decorative icon from screen readers", () => {
    const { body } = render(Icon, { props: { name: "info" } });
    expect(body).toMatch(/<svg[^>]*aria-hidden="true"/);
  });

  it("names an icon that carries meaning", () => {
    const { body } = render(Icon, { props: { name: "info", label: "Info" } });
    expect(body).toMatch(/<svg[^>]*role="img"/);
    expect(body).toMatch(/<svg[^>]*aria-label="Info"/);
    expect(body).not.toContain('aria-hidden="true"');
  });

  it("draws at the requested size", () => {
    const { body } = render(Icon, { props: { name: "x", size: 12 } });
    expect(body).toMatch(/<svg[^>]*width="12"/);
  });
});
