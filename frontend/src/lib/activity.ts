/**
 * Paging for the Activity feed.
 *
 * While only the first page is loaded it follows the archive live. Once more pages are
 * loaded, the first page is frozen: events carry no id, so merging a refreshed first page into
 * the loaded ones could duplicate or drop events with equal timestamps. The view flags newer
 * events instead, and the user reloads from the top.
 */

import type { ActivityFilter, ActivityPage, EventRow } from "./api";
import { ACTIVITY_FILTERS, TERMS } from "./terms";
import { OUTCOMES } from "./events";
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

/** Return `filter` with one of its filters removed. */
export function without(filter: ActivityFilter, key: keyof ActivityFilter): ActivityFilter {
  const next = { ...filter };
  delete next[key];
  return next;
}

/** One page-local filter the user can remove, with its chip text. */
export interface FilterPart {
  key: keyof ActivityFilter;
  /** Names the filter in "Remove the ... filter". */
  noun: string;
  label: string;
  /** The applied values alone, such as "Fail, Skip", for the Filter menu; none for a toggle. */
  value?: string;
  /** Full text for a label cut short, such as a long reason. */
  title?: string;
}

/** Return each removable filter in a fixed order. */
export function filterParts(filter: ActivityFilter): FilterPart[] {
  const listPart = (key: keyof ActivityFilter, noun: string, name: string, values: string[], title?: string): FilterPart => ({
    key,
    noun,
    label: ACTIVITY_FILTERS.chip(name, values),
    value: values.join(", "),
    ...(title ? { title } : {}),
  });
  const { outcome, reason, group, span, gate, flaky, spotCheck } = filter;
  const parts: (FilterPart | null)[] = [
    outcome ? listPart("outcome", "outcome", ACTIVITY_FILTERS.outcome, outcome.map((o) => OUTCOMES[o].label)) : null,
    gate
      ? listPart(
          "gate",
          "gate",
          ACTIVITY_FILTERS.gate,
          gate.map((g) => g.name),
          gate.map((g) => (g.repo ? `${g.name} in ${g.repo}` : g.name)).join(", "),
        )
      : null,
    reason ? listPart("reason", "reason", ACTIVITY_FILTERS.reason, reason, reason.join(", ")) : null,
    span
      ? { key: "span", noun: "day", label: `${ACTIVITY_FILTERS.days}: ${spanLabel(span)}`, value: spanLabel(span) }
      : null,
    group ? { key: "group", noun: `"${group.label}"`, label: group.label, value: group.label } : null,
    flaky ? { key: "flaky", noun: "flaky", label: ACTIVITY_FILTERS.flakyChip } : null,
    spotCheck
      ? { key: "spotCheck", noun: "spot check", label: ACTIVITY_FILTERS.spotCheckChip }
      : null,
  ];
  return parts.filter((part) => part !== null);
}

/** Return "a", "a and b", or "a, b, and c", with `conjunction` in place of "and" when given. */
function listed(items: string[], conjunction: "and" | "or" = "and"): string {
  if (items.length <= 2) return items.join(` ${conjunction} `);
  return `${items.slice(0, -1).join(", ")}, ${conjunction} ${items.at(-1)}`;
}

/**
 * Return what the feed lists under the page-local filters, for empty-state copy, such as
 * '"Ran and failed" or "Skipped by cache" gate calls of lint on flaky trees'. Picked days are
 * left to `emptyTitle`, which names them in place of the range.
 */
export function activitySubject(filter: ActivityFilter): string {
  const outcomes = filter.outcome?.map((o) => `"${OUTCOMES[o].long}"`);
  let text = outcomes ? `${listed(outcomes, "or")} ${TERMS.calls.many}` : TERMS.calls.many;
  if (filter.group) text += ` in "${filter.group.label}"`;
  if (filter.gate) text += ` of ${listed(filter.gate.map((g) => g.name), "or")}`;
  if (filter.flaky) text += " on flaky trees";
  if (filter.spotCheck) text += " that were spot checks";
  if (filter.reason) text += ` with reason ${listed(filter.reason.map((r) => `"${r}"`), "or")}`;
  return text;
}


/**
 * Return the next step for an empty feed. Under page-local filters it names the filters to
 * remove, since loosening the global filters may not help; otherwise it is the generic hint.
 */
export function activityHint(
  filter: ActivityFilter,
  scope: ScopeText & { recording: boolean | null },
): string {
  const removable = filterParts(filter).map((part) => part.noun);
  if (scope.recording === false || removable.length === 0) return emptyHint(scope);
  const noun = removable.length === 1 ? "filter" : "filters";
  const clear = `Remove the ${listed(removable)} ${noun}`;
  const allTime = scope.range.kind === "preset" && scope.range.preset === "all";
  return allTime ? `${clear}.` : `${clear}, or pick a longer range.`;
}
