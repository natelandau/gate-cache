/**
 * Day selection for charts that drill down: a span of local days, how it narrows a query
 * scope, and the keyboard cursor that charts share. Kept free of the DOM so it can be tested.
 */

import type { QueryScope } from "./api";
import { parseDay, rangeLabel, resolveRange, type RangeSpec } from "./range";
import { nowSeconds } from "./state.svelte";

/** A run of local days, both ends included, as `YYYY-MM-DD`. */
export interface DaySpan {
  from: string;
  to: string;
}

/** Return the span between two days, in either order. */
export function spanOf(a: string, b: string): DaySpan {
  return a <= b ? { from: a, to: b } : { from: b, to: a };
}

/** Select one day, or clear the selection when it is already exactly that day. */
export function toggleDay(current: DaySpan | undefined, day: string): DaySpan | undefined {
  if (current?.from === day && current.to === day) return undefined;
  return { from: day, to: day };
}

export function inSpan(span: DaySpan | undefined, day: string): boolean {
  return span !== undefined && span.from <= day && day <= span.to;
}

function customRange(span: DaySpan): RangeSpec {
  return { kind: "custom", start: span.from, end: span.to };
}

/** Return a display name for a span, such as "Nov 3" or "Nov 3 to Nov 5". */
export function spanLabel(span: DaySpan): string {
  return rangeLabel(customRange(span));
}

/** Return whether a string is a real calendar date as `YYYY-MM-DD`. */
export function isDay(text: string): boolean {
  return parseDay(text) !== null;
}

/**
 * Return `scope` narrowed to the overlap with `span`. A span outside the scope gives an empty
 * window, with `from` equal to `to`, so the page shows empty states rather than ignoring it.
 * The span ends at `now` at the latest, so a span of today compares today so far with the same
 * length before it, like a rolling range does.
 */
export function clampScope(scope: QueryScope, span?: DaySpan, now: number = nowSeconds()): QueryScope {
  if (!span) return scope;
  const bounds = resolveRange(customRange(span), new Date(now * 1000));
  const from = Math.max(bounds.from ?? -Infinity, scope.from ?? -Infinity);
  const to = Math.min(bounds.to ?? Infinity, scope.to ?? Infinity);
  return { ...scope, from, to: Math.max(from, to) };
}

/** Where the keyboard cursor is in a list of days, and where a Shift selection started. */
export interface Cursor {
  at: number;
  anchor: number | null;
}

/**
 * Return the cursor after a key press, and the new selection as first and last index (null to
 * clear) when the key changes it. Return null for keys the chart should not handle.
 *
 * `steps` maps arrow keys to index offsets, so a calendar can move by a week on Left and Right.
 */
export function cursorKey(
  cursor: Cursor,
  event: { key: string; shiftKey: boolean },
  steps: Record<string, number>,
  length: number,
  selected: [number, number] | null,
): { cursor: Cursor; select?: [number, number] | null } | null {
  if (length === 0) return null;
  const { key, shiftKey } = event;
  if (key === "Enter" || key === " ") {
    const same = selected?.[0] === cursor.at && selected[1] === cursor.at;
    return same
      ? { cursor: { at: cursor.at, anchor: null }, select: null }
      : { cursor: { at: cursor.at, anchor: cursor.at }, select: [cursor.at, cursor.at] };
  }
  if (key === "Escape") return { cursor: { at: cursor.at, anchor: null }, select: null };
  let target: number;
  if (key === "Home") target = 0;
  else if (key === "End") target = length - 1;
  else if (Object.hasOwn(steps, key)) target = cursor.at + (steps[key] ?? 0);
  else return null;
  const at = Math.min(length - 1, Math.max(0, target));
  if (!shiftKey) return { cursor: { at, anchor: cursor.anchor } };
  const anchor = cursor.anchor ?? cursor.at;
  return { cursor: { at, anchor }, select: [Math.min(anchor, at), Math.max(anchor, at)] };
}

/** The tooltip hint on a chart whose days scope the page. */
export const PICK_DAY_HINT = "Click to scope the page to this day";

/** Return the first and last index of `days` inside `span`, or null when none are. */
export function selectedRange(days: { day: string }[], span?: DaySpan): [number, number] | null {
  if (!span) return null;
  let first = -1;
  let last = -1;
  days.forEach((d, index) => {
    if (inSpan(span, d.day)) {
      if (first === -1) first = index;
      last = index;
    }
  });
  return first === -1 ? null : [first, last];
}

/** Return the range empty-state copy names: the span as custom days when set, else `range`. */
export function spanRange(range: RangeSpec, span?: DaySpan): RangeSpec {
  return span ? customRange(span) : range;
}

/**
 * Return the keyboard cursor as positions in `days`, from the days it was left on. Keeping
 * days rather than positions holds the cursor and the Shift anchor on the same dates when the
 * list grows or shifts. The cursor falls back to the first picked position, then the last day.
 * The anchor counts only while days are picked.
 */
export function dayCursor(
  days: { day: string }[],
  cursorDay: string | null,
  anchorDay: string | null,
  picked: [number, number] | null,
): Cursor {
  const indexOf = (day: string | null) => (day === null ? -1 : days.findIndex((d) => d.day === day));
  const at = indexOf(cursorDay);
  const anchor = picked ? indexOf(anchorDay) : -1;
  return {
    at: at !== -1 ? at : (picked?.[0] ?? days.length - 1),
    anchor: anchor !== -1 ? anchor : null,
  };
}

/** Return the span between two positions in `days`, or undefined for null or a missing day. */
export function spanAt(days: { day: string }[], range: [number, number] | null): DaySpan | undefined {
  const from = range ? days[range[0]]?.day : undefined;
  const to = range ? days[range[1]]?.day : undefined;
  return from && to ? spanOf(from, to) : undefined;
}
