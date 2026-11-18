/** Shared motion settings, so every animated view change moves at the same pace. */

import { cubicOut } from "svelte/easing";

/** True when the user asked the system for less motion. */
export function prefersReducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Duration of a view change in milliseconds, matching `--dur-slow`, or 0 for reduced motion. */
export function viewChangeMs(): number {
  return prefersReducedMotion() ? 0 : 240;
}

/**
 * LayerChart motion for bars: heights and positions ease to their new values when the data
 * changes. Bars start at their final values, so nothing animates on first paint.
 */
export function barMotion(): { type: "tween"; duration: number; easing: (t: number) => number } {
  return { type: "tween", duration: viewChangeMs(), easing: cubicOut };
}
