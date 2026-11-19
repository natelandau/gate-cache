/**
 * The horizontal shift, in px, that keeps a popover inside the viewport. The popover starts at
 * `left` with `width`; the result is zero when it already fits, negative to pull it left, and
 * positive when it starts left of the gutter. A popover wider than the space left of the gutters
 * aligns to the left gutter.
 */
export function popoverShift(left: number, width: number, viewport: number, gutter: number): number {
  const overflow = left + width - (viewport - gutter);
  const shift = overflow > 0 ? -overflow : 0;
  return Math.max(shift, gutter - left);
}
