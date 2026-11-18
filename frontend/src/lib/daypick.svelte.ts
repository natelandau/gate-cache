/**
 * Pointer and keyboard day picking that the daily bar charts share: click a day, drag across
 * days for a range, or use the keyboard cursor from `createDayCursor`.
 */

import { bandIndexAt } from "./daily";
import { createDayCursor, type DayCursor, type DayCursorSource } from "./daycursor.svelte";
import { spanAt, toggleDay } from "./selection";

export interface DayPick {
  /** The keyboard cursor, for `aria-activedescendant` and key handling. */
  readonly nav: DayCursor;
  /** First and last position to draw as picked: a drag in progress, else the picked days. */
  readonly shown: [number, number] | null;
  /** The plot's padding in pixels, so an overlay covers only the plot. */
  readonly padding: { top: number; right: number; bottom: number; left: number };
  /** The band scale's padding, so overlay columns line up with the bars. */
  readonly bandPadding: number;
  /**
   * The index of the day under the pointer, or null in the gap between bars or off the plot.
   * Pass `box` when the caller already measured the frame.
   */
  indexAt(event: PointerEvent, box?: DOMRect): number | null;
  /** The focusable listbox over the plot; bind it with `bind:this`. */
  listbox: HTMLElement | undefined;
  onpointerdown(event: PointerEvent): void;
  onpointermove(event: PointerEvent): void;
  onpointerup(): void;
  /** Drop a drag without picking, for pointer cancel and lost capture. */
  cancel(): void;
}

/**
 * Create day picking for a chart during component initialization. `source` returns the chart's
 * current props; `padding` is the plot's padding in pixels, and `bandPadding`
 * the band scale's padding, so a pointer position maps to the day under it.
 */
export function createDayPick(
  source: () => DayCursorSource,
  padding: { top: number; right: number; bottom: number; left: number },
  bandPadding: number,
): DayPick {
  const nav = createDayCursor(source, { ArrowLeft: -1, ArrowRight: 1 });
  // A drag in progress, shown in place of the picked days until the pointer is released.
  let drag = $state<{ anchor: number; at: number } | null>(null);
  const shown = $derived<[number, number] | null>(
    drag ? [Math.min(drag.anchor, drag.at), Math.max(drag.anchor, drag.at)] : nav.picked,
  );
  let listbox: HTMLElement | undefined = $state();
  // The plot's box, read once per drag rather than on every pointer move.
  let box: DOMRect | null = null;

  // A drag in progress clamps to the plot, so a fast drag past either end reaches the edge day.
  function locate(event: PointerEvent, box: DOMRect, clamp = false): number | null {
    const width = box.width - padding.left - padding.right;
    const fraction = (event.clientX - box.left - padding.left) / width;
    const count = source().days.length;
    return bandIndexAt(clamp ? Math.min(1, Math.max(0, fraction)) : fraction, count, bandPadding);
  }

  return {
    nav,
    padding,
    bandPadding,
    indexAt(event, box) {
      return locate(event, box ?? (event.currentTarget as HTMLElement).getBoundingClientRect());
    },
    get shown() {
      return shown;
    },
    get listbox() {
      return listbox;
    },
    set listbox(element) {
      listbox = element;
    },
    onpointerdown(event) {
      if (event.button !== 0) return;
      box = (event.currentTarget as HTMLElement).getBoundingClientRect();
      const index = locate(event, box);
      if (index === null) return;
      (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
      drag = { anchor: index, at: index };
    },
    onpointermove(event) {
      if (!drag) return;
      const index = box ? locate(event, box, true) : null;
      if (index !== null && index !== drag.at) drag = { anchor: drag.anchor, at: index };
    },
    onpointerup() {
      if (!drag) return;
      const { anchor, at } = drag;
      drag = null;
      nav.move(at, anchor);
      const { days, selected, onselect } = source();
      const day = days[at]?.day;
      if (anchor === at && day) onselect?.(toggleDay(selected, day));
      else onselect?.(spanAt(days, [Math.min(anchor, at), Math.max(anchor, at)]));
      // Arrow keys continue from the day just picked without tabbing in first.
      listbox?.focus({ preventScroll: true });
    },
    cancel() {
      drag = null;
    },
  };
}
