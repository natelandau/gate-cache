/**
 * Keyboard and Shift-pick state that day charts share. The cursor and anchor are kept as days,
 * so they stay on the same dates when the chart's list of days changes.
 */

import {
  cursorKey,
  dayCursor,
  selectedRange,
  spanAt,
  type Cursor,
  type DaySpan,
} from "./selection";

export interface DayCursorSource {
  days: { day: string }[];
  selected?: DaySpan;
  onselect?: (span: DaySpan | undefined) => void;
}

export interface DayCursor {
  /** The cursor and Shift anchor as positions in the current days. */
  readonly cursor: Cursor;
  /** First and last position of the picked days, or null. */
  readonly picked: [number, number] | null;
  /** Put the cursor and anchor on the days at these positions. */
  move(at: number, anchor: number | null): void;
  /** Handle a key from `cursorKey`; returns false for keys the chart does not handle. */
  key(event: KeyboardEvent): boolean;
}

/**
 * Create the cursor for a chart during component initialization. `source` returns the chart's
 * current props; `steps` maps arrow keys to position offsets.
 */
export function createDayCursor(source: () => DayCursorSource, steps: Record<string, number>): DayCursor {
  let cursorDay: string | null = $state(null);
  let anchorDay: string | null = $state(null);
  const picked = $derived(selectedRange(source().days, source().selected));
  const cursor = $derived(dayCursor(source().days, cursorDay, anchorDay, picked));

  function move(at: number, anchor: number | null): void {
    const { days } = source();
    cursorDay = days[at]?.day ?? null;
    anchorDay = anchor === null ? null : (days[anchor]?.day ?? null);
  }

  return {
    get cursor() {
      return cursor;
    },
    get picked() {
      return picked;
    },
    move,
    key(event) {
      const { days, onselect } = source();
      const result = cursorKey(cursor, event, steps, days.length, picked);
      if (!result) return false;
      event.preventDefault();
      move(result.cursor.at, result.cursor.anchor);
      if (result.select !== undefined) onselect?.(spanAt(days, result.select));
      return true;
    },
  };
}
