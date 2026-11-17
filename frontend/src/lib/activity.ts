/**
 * Paging for the Activity feed.
 *
 * While only the first page is loaded it follows the archive live. Once more pages are
 * loaded, the first page is frozen: events carry no id, so merging a refreshed first page into
 * the loaded ones could duplicate or drop events with equal timestamps. The view flags newer
 * events instead, and the user reloads from the top.
 */

import type { ActivityPage, EventRow, Outcome } from "./api";
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
 * '"Fail" runs', or '"Uncached" runs with reason "..."'.
 */
export function activitySubject(filter: { outcome?: Outcome; reason?: string }): string {
  const runs = filter.outcome ? `"${OUTCOMES[filter.outcome].label}" runs` : "runs";
  return filter.reason ? `${runs} with reason "${filter.reason}"` : runs;
}

/**
 * Return the next step for an empty feed. Under an outcome or reason filter it names the filter
 * to clear, since loosening the global filters may not help; otherwise it is the generic hint.
 */
export function activityHint(
  filter: { outcome?: Outcome; reason?: string },
  scope: ScopeText & { recording: boolean | null },
): string {
  if (scope.recording === false || (!filter.outcome && !filter.reason)) return emptyHint(scope);
  const steps: string[] = [];
  if (filter.outcome) steps.push("Pick All outcomes");
  if (filter.reason) steps.push(steps.length ? "remove the reason filter" : "Remove the reason filter");
  const clear = steps.join(" and ");
  const allTime = scope.range.kind === "preset" && scope.range.preset === "all";
  return allTime ? `${clear}.` : `${clear}, or pick a longer range.`;
}
