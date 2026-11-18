/**
 * Paging for the Activity feed.
 *
 * While only the first page is loaded it follows the archive live. Once more pages are
 * loaded, the first page is frozen: events carry no id, so merging a refreshed first page into
 * the loaded ones could duplicate or drop events with equal timestamps. The view flags newer
 * events instead, and the user reloads from the top.
 */

import type { ActivityFilter, ActivityPage, EventRow } from "./api";
import { TERMS } from "./terms";
import { OUTCOMES } from "./events";
import { hourLabel, weekdayName } from "./heat";
import { spanLabel } from "./selection";
import { emptyHint, type ScopeText } from "./scope";

export const PAGE_SIZE = 100;

/** The first page as it was when the user loaded more, plus every page loaded since. */
export interface PagedFeed {
  first: ActivityPage;
  rest: EventRow[];
  /** Cursor for the page after the last one loaded, or null at the end. */
  next: string | null;
  /** The filters the pages were loaded under, serialized; pages for other filters are stale. */
  inputs: string;
}

export interface FeedView {
  events: EventRow[];
  next: string | null;
  /** The live first page has events newer than the frozen one. */
  newer: boolean;
}

/**
 * Add a further page loaded under `inputs`. `live` becomes the frozen first page when nothing
 * was paged yet, or when the existing pages belong to other inputs.
 */
export function addPage(
  paged: PagedFeed | null,
  live: ActivityPage,
  page: ActivityPage,
  inputs: string,
): PagedFeed {
  const base =
    paged?.inputs === inputs ? paged : { first: live, rest: [], next: live.next_before, inputs };
  return { first: base.first, rest: [...base.rest, ...page.events], next: page.next_before, inputs };
}

/** Return what the feed shows given the live first page, any paged state, and the current inputs. */
export function feedView(
  live: ActivityPage | undefined,
  paged: PagedFeed | null,
  inputs: string,
): FeedView {
  if (!paged || paged.inputs !== inputs) {
    return { events: live?.events ?? [], next: live?.next_before ?? null, newer: false };
  }
  const latest = live?.events[0];
  const frozen = paged.first.events[0];
  return {
    events: [...paged.first.events, ...paged.rest],
    next: paged.next,
    newer: latest !== undefined && (frozen === undefined || latest.ts > frozen.ts),
  };
}

/** Return a weekday and hour slot as "Tuesdays 09:00 to 10:00". */
export function slotLabel(slot: { weekday: number; hour: number }): string {
  return `${weekdayName(slot.weekday, "long")}s ${hourLabel(slot.hour)} to ${hourLabel(slot.hour + 1)}`;
}

/** One page-local filter the user can remove, with its chip text and the filter without it. */
export interface FilterPart {
  key: string;
  /** Names the filter in "Remove the ... filter". */
  noun: string;
  label: string;
  /** Full text for a label cut short, such as a long reason. */
  title?: string;
  without: ActivityFilter;
}

/**
 * Return each removable filter in a fixed order. The outcome is left out, since it has its own
 * control.
 */
export function filterParts(filter: ActivityFilter): FilterPart[] {
  const omit = (key: keyof ActivityFilter): ActivityFilter => {
    const next = { ...filter };
    delete next[key];
    return next;
  };
  const { reason, group, span, slot, gate, flaky } = filter;
  const parts: (FilterPart | null)[] = [
    reason ? { key: "reason", noun: "reason", label: `Reason: ${reason}`, title: reason, without: omit("reason") } : null,
    group ? { key: "group", noun: `"${group.label}"`, label: group.label, without: omit("group") } : null,
    span ? { key: "span", noun: "day", label: `Days: ${spanLabel(span)}`, without: omit("span") } : null,
    slot ? { key: "slot", noun: "hour", label: slotLabel(slot), without: omit("slot") } : null,
    gate
      ? {
          key: "gate",
          noun: "gate",
          label: `Gate: ${gate.name}`,
          title: gate.repo ? `${gate.name} in ${gate.repo}` : gate.name,
          without: omit("gate"),
        }
      : null,
    flaky ? { key: "flaky", noun: "flaky", label: "Flaky trees only", without: omit("flaky") } : null,
  ];
  return parts.filter((part) => part !== null);
}

/**
 * Return what the feed lists under the page-local filters, for empty-state copy, such as
 * '"Ran and failed" gate calls of lint on flaky trees'. Picked days are left to `emptyTitle`, which names
 * them in place of the range.
 */
export function activitySubject(filter: ActivityFilter): string {
  let text = filter.outcome ? `"${OUTCOMES[filter.outcome].long}" ${TERMS.calls.many}` : TERMS.calls.many;
  if (filter.group) text += ` in "${filter.group.label}"`;
  if (filter.gate) text += ` of ${filter.gate.name}`;
  if (filter.flaky) text += " on flaky trees";
  if (filter.reason) text += ` with reason "${filter.reason}"`;
  if (filter.slot) text += ` on ${slotLabel(filter.slot)}`;
  return text;
}

function listed(names: string[]): string {
  if (names.length <= 2) return names.join(" and ");
  return `${names.slice(0, -1).join(", ")}, and ${names.at(-1)}`;
}

/**
 * Return the next step for an empty feed. Under page-local filters it names the filters to
 * clear, since loosening the global filters may not help; otherwise it is the generic hint.
 */
export function activityHint(
  filter: ActivityFilter,
  scope: ScopeText & { recording: boolean | null },
): string {
  const removable = filterParts(filter).map((part) => part.noun);
  if (scope.recording === false || (!filter.outcome && removable.length === 0)) return emptyHint(scope);
  const steps: string[] = [];
  if (filter.outcome) steps.push("Pick All outcomes");
  if (removable.length) {
    const noun = removable.length === 1 ? "filter" : "filters";
    steps.push(`${steps.length ? "remove" : "Remove"} the ${listed(removable)} ${noun}`);
  }
  const clear = steps.join(" and ");
  const allTime = scope.range.kind === "preset" && scope.range.preset === "all";
  return allTime ? `${clear}.` : `${clear}, or pick a longer range.`;
}
