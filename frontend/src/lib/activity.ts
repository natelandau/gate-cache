/**
 * Paging for the Activity feed.
 *
 * While only the first page is loaded it follows the archive live. Once more pages are
 * loaded, the first page is frozen: events carry no id, so merging a refreshed first page into
 * the loaded ones could duplicate or drop events with equal timestamps. The view flags newer
 * events instead, and the user reloads from the top.
 */

import type { ActivityFilter, ActivityPage, EventRow } from "./api";
import { OUTCOMES } from "./events";
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

/**
 * Return what the feed lists under the page-local filters, for empty-state copy: "runs",
 * '"Fail" runs', '"Uncached" runs with reason "..."', or 'runs in "Branch: main"'.
 */
export function activitySubject(filter: ActivityFilter): string {
  let runs = filter.outcome ? `"${OUTCOMES[filter.outcome].label}" runs` : "runs";
  if (filter.group) runs = `${runs} in "${filter.group.label}"`;
  return filter.reason ? `${runs} with reason "${filter.reason}"` : runs;
}

/**
 * Return the next step for an empty feed. Under a page-local filter it names the filter to
 * clear, since loosening the global filters may not help; otherwise it is the generic hint.
 */
export function activityHint(
  filter: ActivityFilter,
  scope: ScopeText & { recording: boolean | null },
): string {
  const steps: string[] = [];
  if (filter.outcome) steps.push("pick All outcomes");
  if (filter.reason) steps.push("remove the reason filter");
  if (filter.group) steps.push(`remove the "${filter.group.label}" filter`);
  if (scope.recording === false || steps.length === 0) return emptyHint(scope);
  const text = steps.join(" and ");
  const clear = text.charAt(0).toUpperCase() + text.slice(1);
  const allTime = scope.range.kind === "preset" && scope.range.preset === "all";
  return allTime ? `${clear}.` : `${clear}, or pick a longer range.`;
}
