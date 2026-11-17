/**
 * Hash routes for the dashboard. The server serves one page, so all navigation lives in
 * `location.hash`:
 *
 * - `#/overview` (also the default for an empty or unknown hash)
 * - `#/gates`, `#/gates/<repo>/<name>` with each part URI-encoded and `-` for the unknown repo
 * - `#/repos`, `#/repos/<repo>` with the repo URI-encoded
 * - `#/activity`, `#/flaky`
 */

export type Route =
  | { page: "overview" }
  | { page: "gates" }
  | { page: "gate"; repo: string | null; name: string }
  | { page: "repos" }
  | { page: "repo"; repo: string }
  | { page: "activity" }
  | { page: "flaky" };

export type Page = Route["page"];

/** Stands in for a null repo in a gate route; a git common directory is never `-`. */
const UNKNOWN_REPO = "-";

const SIMPLE_PAGES = new Set(["overview", "gates", "repos", "activity", "flaky"]);

function decode(part: string): string | null {
  try {
    return decodeURIComponent(part);
  } catch {
    return null;
  }
}

/** Parse a location hash such as `#/gates` into a route. */
export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/");
  const [head = "", ...rest] = parts;
  if (head === "gates" && rest.length === 2) {
    const repo = decode(rest[0] ?? "");
    const name = decode(rest[1] ?? "");
    if (repo !== null && name) {
      return { page: "gate", repo: repo === UNKNOWN_REPO ? null : repo, name };
    }
  }
  if (head === "repos" && rest.length === 1) {
    const repo = decode(rest[0] ?? "");
    if (repo) return { page: "repo", repo };
  }
  if (rest.length === 0 && SIMPLE_PAGES.has(head)) return { page: head } as Route;
  return { page: "overview" };
}

/** Return the hash href for a route. */
export function href(route: Route): string {
  if (route.page === "gate") {
    const repo = encodeURIComponent(route.repo ?? UNKNOWN_REPO);
    return `#/gates/${repo}/${encodeURIComponent(route.name)}`;
  }
  if (route.page === "repo") return `#/repos/${encodeURIComponent(route.repo)}`;
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
 * Return the repo whose detail page shows for `route`: the repo page itself, or the repo page
 * a gate panel was opened from, which stays underneath the panel. Null for any other page.
 */
export function repoPageRepo(route: Route, opener: Route | null): string | null {
  if (route.page === "repo") return route.repo;
  if (route.page === "gate" && opener?.page === "repo") return opener.repo;
  return null;
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
