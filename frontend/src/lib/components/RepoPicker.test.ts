import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import RepoPicker, { toggleRepo } from "./RepoPicker.svelte";

describe("toggleRepo", () => {
  it("adds a checked repo", () => {
    expect(toggleRepo([], "a", true)).toEqual(["a"]);
    expect(toggleRepo(["a"], "b", true)).toEqual(["a", "b"]);
    expect(toggleRepo(["a"], "a", true)).toEqual(["a"]);
  });

  it("clears every repo when All repos is checked", () => {
    expect(toggleRepo(["a", "b"], null, true)).toEqual([]);
  });

  it("returns to all repos when the last repo is unchecked", () => {
    expect(toggleRepo(["a"], "a", false)).toEqual([]);
    expect(toggleRepo(["a", "b"], "a", false)).toEqual(["b"]);
  });
});

describe("RepoPicker", () => {
  const options = [
    { value: "/w/api/.git", label: "api", title: "/w/api/.git" },
    { value: "/w/web/.git", label: "web", title: "/w/web/.git" },
    { value: "-", label: "unknown repo" },
  ];

  it("labels the button by the selection", () => {
    const label = (value: string[]) =>
      /<span class="label[^"]*">([^<]*)<\/span>/.exec(
        render(RepoPicker, { props: { options, value, onchange: () => {} } }).body,
      )?.[1];
    expect(label([])).toBe("All repos");
    expect(label(["/w/web/.git"])).toBe("web");
    expect(label(["/w/web/.git", "-"])).toBe("2 repos");
  });

  it("lists All repos first and checks only the selected repos", () => {
    const { body } = render(RepoPicker, { props: { options, value: ["-"], onchange: () => {} } });
    const boxes = [...body.matchAll(/<input type="checkbox"[^>]*>/g)].map((m) => m[0]);
    expect(boxes).toHaveLength(4);
    expect(boxes.map((b) => b.includes("checked"))).toEqual([false, false, false, true]);
    expect(body.indexOf("All repos</span>")).toBeLessThan(body.indexOf("<hr"));
    expect(body.indexOf("<hr")).toBeLessThan(body.indexOf(">api<"));
  });
});
