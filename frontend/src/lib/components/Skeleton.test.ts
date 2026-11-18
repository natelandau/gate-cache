import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import Skeleton from "./Skeleton.svelte";


describe("Skeleton", () => {
  it("is hidden from screen readers and sized by its props", () => {
    const { body } = render(Skeleton, { props: { height: 14, width: "40%" } });
    expect(body).toContain('aria-hidden="true"');
    expect(body).toContain("height: 14px");
    expect(body).toContain("width: 40%");
  });

});
