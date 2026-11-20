/**
 * Hash routes for the dashboard. The server serves one page, so all navigation lives in
 * `location.hash`:
 *
 * - `#/overview` (also the default for an empty or unknown hash), with an optional
 *   `?from=<day>&to=<day>` span of local days
 * - `#/gates`, `#/gates/<repo>/<name>` with each part URI-encoded and `-` for the unknown repo
 * - `#/activity`, with optional `outcome`, `reason`, `from`, `to`, `gate`, `flaky`, and
 *   `spot_check` filters, URI-encoded, and an optional Breakdown row as
 *   `group=<dimension>&key=<key>&label=<chip text>`. `outcome`, `reason`, and `gate` repeat once
 *   per value, and each `gate` is `<repo>\0<name>`, as in the API.
 * - `#/triage`, with an optional `reason` filter
 *
 * Spans and activity filters are page-local: they live only in the hash. A malformed one is
 * dropped, not an error.
 */

import type { ActivityFilter, ActivityLink, GateRef, Outcome, TriageReason } from "./api";
import { dimension, isDimension } from "./dimensions";
import { OUTCOMES } from "./events";
import { hasKey } from "./guards";
import { isDay, spanOf, type DaySpan } from "./selection";
import { isTriageReason } from "./triage";

export type Route =
  | { page: "overview"; span?: DaySpan }
  | { page: "gates" }
  | { page: "gate"; repo: string | null; name: string }
  | ({ page: "activity" } & ActivityFilter)
  | { page: "triage"; reason?: TriageReason };

export type Page = Route["page"];

/**
 * Stands in for a null repo in gate routes, API repo parameters, and repo filters; a git
 * common directory is never `-`.
 */
export const UNKNOWN_REPO = "-";

const SIMPLE_PAGES = new Set(["overview", "gates", "activity", "triage"]);

function decode(part: string): string | null {
  try {
    return decodeURIComponent(part);
  } catch {
    return null;
  }
}

function isOutcome(value: string): value is Outcome {
  return hasKey(OUTCOMES, value);
}

/** Return the distinct values of a repeated parameter that pass `keep`, in order. */
function listParam<T extends string>(params: URLSearchParams, key: string, keep: (value: string) => value is T): T[] {
  return [...new Set(params.getAll(key).filter(keep))];
}

function isText(value: string): value is string {
  return value !== "";
}

// A NUL joins a gate's repo and name, since neither a path nor a command holds one.
const GATE_SEPARATOR = "\0";

/** Return a gate as one `gate` parameter value: its repo and name joined by a NUL. */
export function gateParam(gate: GateRef): string {
  return `${gate.repo ?? UNKNOWN_REPO}${GATE_SEPARATOR}${gate.name}`;
}

/** Return the gate a `gate` parameter value names, or null when it lacks a repo or a name. */
export function parseGateParam(value: string): GateRef | null {
  const at = value.indexOf(GATE_SEPARATOR);
  const repo = value.slice(0, at);
  const name = value.slice(at + 1);
  if (at === -1 || !repo || !name) return null;
  return { repo: repo === UNKNOWN_REPO ? null : repo, name };
}

/** Return the distinct gates of repeated `gate` parameters, in order, dropping malformed ones. */
function parseGates(params: URLSearchParams): GateRef[] {
  const values = [...new Set(params.getAll("gate"))];
  return values.map(parseGateParam).filter((gate) => gate !== null);
}

function parseSpan(params: URLSearchParams): DaySpan | undefined {
  const from = params.get("from");
  const to = params.get("to");
  return from && to && isDay(from) && isDay(to) ? spanOf(from, to) : undefined;
}

function activityRoute(query: string): Route {
  const params = new URLSearchParams(query);
  const outcome = listParam(params, "outcome", isOutcome);
  const reason = listParam(params, "reason", isText);
  const by = params.get("group");
  const key = params.get("key");
  const span = parseSpan(params);
  const gate = parseGates(params);
  return {
    page: "activity",
    ...(outcome.length ? { outcome } : {}),
    ...(reason.length ? { reason } : {}),
    ...(isDimension(by) && key ? { group: { by, key, label: params.get("label") || dimension(by).label } } : {}),
    ...(span ? { span } : {}),
    ...(gate.length ? { gate } : {}),
    ...(params.get("flaky") === "1" ? { flaky: true as const } : {}),
    ...(params.get("spot_check") === "1" ? { spotCheck: true as const } : {}),
  };
}

function triageRoute(query: string): Route {
  const reason = new URLSearchParams(query).get("reason");
  return isTriageReason(reason) ? { page: "triage", reason } : { page: "triage" };
}

function overviewRoute(query: string): Route {
  const span = parseSpan(new URLSearchParams(query));
  return span ? { page: "overview", span } : { page: "overview" };
}

/**
 * Return the query parameters of an activity filter, except its span, in the names both the
 * hash route and the API use. The API takes the span as Unix seconds, not days.
 */
export function activityParams(filter: Omit<ActivityFilter, "span">): Record<string, string | string[]> {
  const params: Record<string, string | string[]> = {};
  if (filter.outcome) params.outcome = filter.outcome;
  if (filter.reason) params.reason = filter.reason;
  if (filter.gate) params.gate = filter.gate.map(gateParam);
  if (filter.flaky) params.flaky = "1";
  if (filter.spotCheck) params.spot_check = "1";
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
    .flatMap(([key, value]) => [value].flat().map((item) => `${key}=${encodeURIComponent(item)}`))
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
  if (head === "activity" && rest.length === 0) return activityRoute(query);
  if (head === "overview" && rest.length === 0) return overviewRoute(query);
  if (head === "triage" && rest.length === 0) return triageRoute(query);
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
  if (route.page === "triage" && route.reason) return `#/triage?reason=${encodeURIComponent(route.reason)}`;
  return `#/${route.page}`;
}

/** Return the filter a link sets, with each single value as a one-item list. */
export function linkFilter(link: ActivityLink): ActivityFilter {
  const { outcome, reason, gate, ...rest } = link;
  return {
    ...rest,
    ...(outcome ? { outcome: [outcome] } : {}),
    ...(reason ? { reason: [reason] } : {}),
    ...(gate ? { gate: [gate] } : {}),
  };
}

/** Return the Activity link for a filter, narrowed to `span` when one is given. */
export function activityHref(link: ActivityLink, span?: DaySpan): string {
  return href({ page: "activity", ...linkFilter(link), ...(span ? { span } : {}) });
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
    const next = parseHash(location.hash);
    const replaced = pendingReplace;
    pendingReplace = false;
    router.opener = openerAfter(loaded ? router.route : null, next, router.opener, replaced);
    router.route = next;
    loaded = true;
  };
  sync();
  window.addEventListener("hashchange", sync);
  return () => window.removeEventListener("hashchange", sync);
}
