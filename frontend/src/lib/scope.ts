/** Copy that names the active filters, for empty states. */

import { type RangeSpec, rangeLabel } from "./range";

export interface ScopeText {
  range: RangeSpec;
  /** Display name of the repo selection, or null for all repos. */
  repoLabel: string | null;
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
  if (isAllTime(scope.range)) return `No ${subject} recorded${repo || " yet"}.`;
  return `No ${subject} ${rangePhrase(scope.range)}${repo}.`;
}

/** Return the next step for an empty page: turn recording on, or loosen a filter. */
export function emptyHint(scope: ScopeText & { recording: boolean | null }): string {
  if (scope.recording === false) {
    return "Turn recording on with gate-cache stats on, then run a gate through gate-cache.";
  }
  if (scope.repoLabel) return "Pick All repos or a longer range.";
  if (!isAllTime(scope.range)) return "Run a gate through gate-cache, or pick a longer range.";
  return "Run a gate through gate-cache.";
}
