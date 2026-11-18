/** Shared motion settings, so every animated view change moves at the same pace. */

import { cubicOut } from "svelte/easing";

/** True when the user asked the system for less motion. */
export function prefersReducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Duration of a view change in milliseconds. `app.css.test.ts` keeps `--dur-slow` equal to it. */
export const VIEW_CHANGE_MS = 240;

/** Duration of a view change in milliseconds, or 0 for reduced motion. */
export function viewChangeMs(): number {
  return prefersReducedMotion() ? 0 : VIEW_CHANGE_MS;
}

type Tween = { type: "tween"; duration: number; easing: (t: number) => number };

/**
 * LayerChart motion for bars: each bar's top and height ease to new values when the data
 * changes. Only y and height animate, so a window resize redraws at once and each bar keeps two
 * tweens rather than five. Under reduced motion there is no motion at all.
 */
export function barMotion(): { y: Tween; height: Tween } | undefined {
  if (prefersReducedMotion()) return undefined;
  const tween: Tween = { type: "tween", duration: VIEW_CHANGE_MS, easing: cubicOut };
  return { y: tween, height: tween };
}
