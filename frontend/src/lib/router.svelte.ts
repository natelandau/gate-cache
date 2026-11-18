/**
 * Hash routes for the dashboard. The server serves one page, so all navigation lives in
 * `location.hash`:
 *
 * - `#/overview` (also the default for an empty or unknown hash), with an optional
 *   `?from=<day>&to=<day>` span of local days
 * - `#/gates`, `#/gates/<repo>/<name>` with each part URI-encoded and `-` for the unknown repo
 * - `#/activity`, with optional `outcome`, `reason`, `from`, `to`, `weekday`, `hour`, `gate`,
 *   `gate_repo`, and `flaky` filters, URI-encoded, and an optional Breakdown row as
 *   `group=<dimension>&key=<key>&label=<chip text>`
 * - `#/flaky`
 *
 * Spans and activity filters are page-local: they live only in the hash. A malformed one is
 * dropped, not an error.
 *
 * Old `#/repos/<repo>` links parse as the overview with `selectRepo` set; `startRouter` turns
 * that into a repo filter. `startRouter` replaces any old `#/repos` hash with `#/overview`.
 */

import type { ActivityFilter, Outcome } from "./api";
import { dimension, isDimension } from "./dimensions";
import { OUTCOMES } from "./events";
import { isDay, spanOf, type DaySpan } from "./selection";
import { setRepos } from "./state.svelte";

export type Route =
  | { page: "overview"; selectRepo?: string; span?: DaySpan }
  | { page: "gates" }
  | { page: "gate"; repo: string | null; name: string }
  | ({ page: "activity" } & ActivityFilter)
  | { page: "flaky" };

export type Page = Route["page"];

/**
 * Stands in for a null repo in gate routes, API repo parameters, and repo filters; a git
 * common directory is never `-`.
 */
export const UNKNOWN_REPO = "-";

const SIMPLE_PAGES = new Set(["overview", "gates", "activity", "flaky"]);

function decode(part: string): string | null {
  try {
    return decodeURIComponent(part);
  } catch {
    return null;
  }
}

function isOutcome(value: string | null): value is Outcome {
  return value !== null && Object.hasOwn(OUTCOMES, value);
}

function parseSpan(params: URLSearchParams): DaySpan | undefined {
  const from = params.get("from");
  const to = params.get("to");
  return from && to && isDay(from) && isDay(to) ? spanOf(from, to) : undefined;
}

function parseBounded(text: string | null, max: number): number | undefined {
  if (text === null || !/^\d{1,2}$/.test(text)) return undefined;
  const value = Number(text);
  return value <= max ? value : undefined;
}

function activityRoute(query: string): Route {
  const params = new URLSearchParams(query);
  const outcome = params.get("outcome");
  const reason = params.get("reason");
  const by = params.get("group");
  const key = params.get("key");
  const span = parseSpan(params);
  const weekday = parseBounded(params.get("weekday"), 6);
  const hour = parseBounded(params.get("hour"), 23);
  const gate = params.get("gate");
  const gateRepo = params.get("gate_repo");
  return {
    page: "activity",
    ...(isOutcome(outcome) ? { outcome } : {}),
    ...(reason ? { reason } : {}),
    ...(isDimension(by) && key ? { group: { by, key, label: params.get("label") || dimension(by).label } } : {}),
    ...(span ? { span } : {}),
    ...(weekday !== undefined && hour !== undefined ? { slot: { weekday, hour } } : {}),
    ...(gate && gateRepo ? { gate: { repo: gateRepo === UNKNOWN_REPO ? null : gateRepo, name: gate } } : {}),
    ...(params.get("flaky") === "1" ? { flaky: true as const } : {}),
  };
}

function overviewRoute(query: string): Route {
  const span = parseSpan(new URLSearchParams(query));
  return span ? { page: "overview", span } : { page: "overview" };
}

/**
 * Return the query parameters of an activity filter, except its span, in the names both the
 * hash route and the API use. The API takes the span as Unix seconds, not days.
 */
export function activityParams(filter: Omit<ActivityFilter, "span">): Record<string, string> {
  const params: Record<string, string> = {};
  if (filter.outcome) params.outcome = filter.outcome;
  if (filter.reason) params.reason = filter.reason;
  if (filter.slot) {
    params.weekday = String(filter.slot.weekday);
    params.hour = String(filter.slot.hour);
  }
  if (filter.gate) {
    params.gate = filter.gate.name;
    params.gate_repo = filter.gate.repo ?? UNKNOWN_REPO;
  }
  if (filter.flaky) params.flaky = "1";
  if (filter.group) {
    params.group = filter.group.by;
    params.key = filter.group.key;
  }
  return params;
}

function activityQuery(filter: ActivityFilter): string {
  // The chip label rides in the hash only; the API never needs it.
  const label = filter.group ? { label: filter.group.label } : {};
  const params = { ...activityParams(filter), ...label, ...(filter.span ?? {}) };
  return Object.entries(params)
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join("&");
}

/** Parse a location hash such as `#/gates` into a route. */
export function parseHash(hash: string): Route {
  const body = hash.replace(/^#\/?/, "");
  const mark = body.indexOf("?");
  const path = mark === -1 ? body : body.slice(0, mark);
  const query = mark === -1 ? "" : body.slice(mark + 1);
  const [head = "", ...rest] = path.split("/");
  if (head === "gates" && rest.length === 2) {
    const repo = decode(rest[0] ?? "");
    const name = decode(rest[1] ?? "");
    if (repo !== null && name) {
      return { page: "gate", repo: repo === UNKNOWN_REPO ? null : repo, name };
    }
  }
  if (head === "repos" && rest.length === 1) {
    const repo = decode(rest[0] ?? "");
    if (repo) return { page: "overview", selectRepo: repo };
  }
  if (head === "activity" && rest.length === 0) return activityRoute(query);
  if (head === "overview" && rest.length === 0) return overviewRoute(query);
  if (rest.length === 0 && SIMPLE_PAGES.has(head)) return { page: head } as Route;
  return { page: "overview" };
}

/** Return the hash href for a route. */
export function href(route: Route): string {
  if (route.page === "gate") {
    const repo = encodeURIComponent(route.repo ?? UNKNOWN_REPO);
    return `#/gates/${repo}/${encodeURIComponent(route.name)}`;
  }
  if (route.page === "activity") {
    const query = activityQuery(route);
    return query ? `#/activity?${query}` : "#/activity";
  }
  if (route.page === "overview" && route.span) {
    return `#/overview?from=${route.span.from}&to=${route.span.to}`;
  }
  return `#/${route.page}`;
}

/** Return the Activity link for a filter, narrowed to `span` when one is given. */
export function activityHref(filter: ActivityFilter, span?: DaySpan): string {
  return href({ page: "activity", ...filter, ...(span ? { span } : {}) });
}

/**
 * The current route, and the page a gate panel was opened from (null when the app loaded on a
 * gate or no gate is open). Both follow `hashchange` once `startRouter` runs.
 */
export const router: { route: Route; opener: Route | null } = $state({
  route: { page: "overview" },
  opener: null,
});

/**
 * Return the opener after moving from `current` (null on first load) to `next`. Switching
 * between gates inside the panel (`replaced`) keeps the original opener; any other switch
 * between gates, such as an edit in the address bar, has none, because going back would only
 * return to the previous gate.
 */
export function openerAfter(
  current: Route | null,
  next: Route,
  opener: Route | null,
  replaced = false,
): Route | null {
  if (next.page !== "gate" || current === null) return null;
  if (current.page !== "gate") return current;
  return replaced ? opener : null;
}

/**
 * Return the page a gate panel opens over: the overview when the gate was opened from it, the
 * Gates page for any other open gate, and null when no gate is open.
 */
export function panelHost(route: Route, opener: Route | null): "overview" | "gates" | null {
  if (route.page !== "gate") return null;
  return opener?.page === "overview" ? "overview" : "gates";
}

/** Return whether a hash is an old `#/repos` route, which the overview replaced. */
function isReposHash(hash: string): boolean {
  return /^#?\/?repos(?:[/?]|$)/.test(hash);
}

/** Set by `navigate` with `replace` and consumed by the next hash change. */
let pendingReplace = false;

/**
 * Navigate to a route by changing the hash. `replace` swaps the current history entry instead of
 * adding one, so switching gates in the panel leaves one entry to go back from.
 */
export function navigate(route: Route, options: { replace?: boolean } = {}): void {
  const target = href(route);
  if (options.replace) {
    // Replacing with the current hash fires no hashchange, so the flag would never be consumed.
    pendingReplace = target !== location.hash;
    location.replace(target);
  } else {
    location.hash = target;
  }
}

/** Track the location hash; returns a function that stops tracking. */
export function startRouter(): () => void {
  let loaded = false;
  const sync = () => {
    let next = parseHash(location.hash);
    const replaced = pendingReplace;
    pendingReplace = false;
    if (next.page === "overview" && isReposHash(location.hash)) {
      if (next.selectRepo !== undefined) setRepos([next.selectRepo]);
      next = { page: "overview" };
      navigate(next, { replace: true });
    }
    router.opener = openerAfter(loaded ? router.route : null, next, router.opener, replaced);
    router.route = next;
    loaded = true;
  };
  sync();
  window.addEventListener("hashchange", sync);
  return () => window.removeEventListener("hashchange", sync);
}
