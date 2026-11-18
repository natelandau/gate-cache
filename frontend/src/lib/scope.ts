/** Copy that names the active filters, for empty states. */

import { type RangeSpec, rangeLabel } from "./range";
import { spanRange, type DaySpan } from "./selection";

export interface ScopeText {
  range: RangeSpec;
  /** Display name of the repo selection, or null for all repos. */
  repoLabel: string | null;
  /** Days picked on a chart, which the copy names in place of the range. */
  span?: DaySpan;
}

/** Return the range as it reads inside a sentence, such as "in the last 7 days" or "this month". */
function rangePhrase(range: RangeSpec): string {
  const label = rangeLabel(range);
  switch (range.kind) {
    case "preset":
      return `in the ${label.replace(/^Last/, "last")}`;
    case "period":
      return label.charAt(0).toLowerCase() + label.slice(1);
    case "custom":
      return range.start === range.end ? `on ${label}` : `from ${label}`;
  }
}

function isAllTime(range: RangeSpec): boolean {
  return range.kind === "preset" && range.preset === "all";
}

/**
 * Return an empty-state title that names the filters, such as
 * "No runs in the last 7 days for api-server."
 */
export function emptyTitle(subject: string, scope: ScopeText): string {
  const repo = scope.repoLabel ? ` for ${scope.repoLabel}` : "";
  const range = spanRange(scope.range, scope.span);
  if (isAllTime(range)) return `No ${subject} recorded${repo || " yet"}.`;
  return `No ${subject} ${rangePhrase(range)}${repo}.`;
}

/**
 * Return the next step for an empty page: turn recording on, or loosen a filter. Days picked
 * on a chart are the filter to loosen first.
 */
export function emptyHint(scope: ScopeText & { recording: boolean | null }): string {
  if (scope.recording === false) {
    return "Turn recording on with gate-cache stats on, then run a gate through gate-cache.";
  }
  if (scope.span) return "Pick other days, or remove the day filter.";
  if (scope.repoLabel) return "Pick All repos or a longer range.";
  if (!isAllTime(scope.range)) return "Run a gate through gate-cache, or pick a longer range.";
  return "Run a gate through gate-cache.";
}
