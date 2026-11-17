/** Copy that names the active filters, for empty states. */

import { RANGES, type Range } from "./state.svelte";

export interface ScopeText {
  range: Range;
  /** Display name of the selected repo, or null for all repos. */
  repoLabel: string | null;
}

/**
 * Return an empty-state title that names the filters, such as
 * "No runs in the last 7 days for api-server."
 */
export function emptyTitle(subject: string, scope: ScopeText): string {
  const repo = scope.repoLabel ? ` for ${scope.repoLabel}` : "";
  if (scope.range === "all") return `No ${subject} recorded${repo || " yet"}.`;
  const range = RANGES.find((r) => r.value === scope.range)?.long ?? scope.range;
  return `No ${subject} in the ${range.replace(/^Last/, "last")}${repo}.`;
}

/** Return the next step for an empty page: turn recording on, or loosen a filter. */
export function emptyHint(scope: ScopeText & { recording: boolean | null }): string {
  if (scope.recording === false) {
    return "Turn recording on with gate-cache stats on, then run a gate through gate-cache.";
  }
  if (scope.repoLabel) return "Pick All repos or a longer range.";
  if (scope.range !== "all") return "Run a gate through gate-cache, or pick a longer range.";
  return "Run a gate through gate-cache.";
}
