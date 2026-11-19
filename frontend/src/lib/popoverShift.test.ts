import { describe, expect, it } from "vitest";
import { popoverShift } from "./popoverShift";

describe("popoverShift", () => {
  it.each([
    ["fits", 100, 200, 1000, 16, 0],
    ["overflows right", 200, 300, 390, 16, -126],
    ["flush to the right gutter", 16, 358, 390, 16, 0],
    ["wider than the room", 100, 460, 390, 16, -84],
  ])("%s", (_name, left, width, viewport, gutter, expected) => {
    expect(popoverShift(left, width, viewport, gutter)).toBe(expected);
  });
});
