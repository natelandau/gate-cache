/**
 * Hash routes for the dashboard. The server serves one page, so all navigation lives in
 * `location.hash`:
 *
 * - `#/overview` (also the default for an empty or unknown hash)
 * - `#/gates`, `#/gates/<repo>/<name>` with each part URI-encoded and `-` for the unknown repo
 * - `#/activity`, with optional `?outcome=<outcome>&reason=<reason>` filters, URI-encoded
 * - `#/flaky`
 *
 * Old `#/repos/<repo>` links parse as the overview with `selectRepo` set; `startRouter` turns
 * that into a repo filter. `startRouter` replaces any old `#/repos` hash with `#/overview`.
 */

import type { Outcome } from "./api";
import { OUTCOMES } from "./events";
import { setRepos } from "./state.svelte";

export type Route =
  | { page: "overview"; selectRepo?: string }
  | { page: "gates" }
  | { page: "gate"; repo: string | null; name: string }
  | { page: "activity"; outcome?: Outcome; reason?: string }
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

function activityRoute(query: string): Route {
  const params = new URLSearchParams(query);
  const outcome = params.get("outcome");
  const reason = params.get("reason");
  return {
    page: "activity",
    ...(isOutcome(outcome) ? { outcome } : {}),
    ...(reason ? { reason } : {}),
  };
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
    const params: string[] = [];
    if (route.outcome) params.push(`outcome=${encodeURIComponent(route.outcome)}`);
    if (route.reason) params.push(`reason=${encodeURIComponent(route.reason)}`);
    return params.length ? `#/activity?${params.join("&")}` : "#/activity";
  }
  return `#/${route.page}`;
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
