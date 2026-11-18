import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import Skeleton from "./Skeleton.svelte";

const fs = (await import(/* @vite-ignore */ ["node", "fs"].join(":"))) as {
  readFileSync(path: URL, encoding: "utf8"): string;
};
const source = fs.readFileSync(new URL("./Skeleton.svelte", import.meta.url), "utf8");

describe("Skeleton", () => {
  it("is hidden from screen readers and sized by its props", () => {
    const { body } = render(Skeleton, { props: { height: 14, width: "40%" } });
    expect(body).toContain('aria-hidden="true"');
    expect(body).toContain("height: 14px");
    expect(body).toContain("width: 40%");
  });

  it("does not loop an animation, since the live dot is the only loop", () => {
    expect(source).not.toContain("infinite");
  });
});
