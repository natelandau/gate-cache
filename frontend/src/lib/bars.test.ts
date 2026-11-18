import { describe, expect, it } from "vitest";
import { barFloor, MIN_BAR_PX, stackStretch, visibleValue } from "./bars";

describe("visibleValue", () => {
  it.each([
    { value: 0, floor: 5, expected: 0 },
    { value: 1, floor: 5, expected: 5 },
    { value: 9, floor: 5, expected: 9 },
  ])("draws $value as $expected with a floor of $floor", ({ value, floor, expected }) => {
    expect(visibleValue(value, floor)).toBe(expected);
  });

  it("draws one run among thousands at least the minimum bar height", () => {
    const top = 2000;
    const plotPx = 232;
    const drawn = visibleValue(1, barFloor(top, plotPx));
    expect((drawn / top) * plotPx).toBeCloseTo(MIN_BAR_PX);
  });

  it("adds no floor before the plot has a size", () => {
    expect(visibleValue(1, barFloor(2000, 0))).toBe(1);
  });
});

describe("stackStretch", () => {
  it("stretches a short stack to the floor and leaves others alone", () => {
    expect(stackStretch(1, 4)).toBe(4);
    expect(stackStretch(10, 4)).toBe(1);
    expect(stackStretch(0, 4)).toBe(1);
  });
});
