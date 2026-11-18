/** Helpers that keep every bar for a non-zero value visible, however tall the tallest bar. */

/** Height, in pixels, of the shortest bar a non-zero value draws. */
export const MIN_BAR_PX = 2;

/** Return the value that draws `MIN_BAR_PX` tall on a y scale from 0 to `top` over `plotPx` pixels. */
export function barFloor(top: number, plotPx: number): number {
  return plotPx > 0 ? (MIN_BAR_PX / plotPx) * top : 0;
}

/** Return `value` raised to `floor` when it is above zero. Zero stays zero, so empty stays empty. */
export function visibleValue(value: number, floor: number): number {
  return value > 0 ? Math.max(value, floor) : value;
}

/** Return how much to stretch a stacked bar of height `total` so it draws at least `floor` tall. */
export function stackStretch(total: number, floor: number): number {
  return total > 0 ? visibleValue(total, floor) / total : 1;
}
