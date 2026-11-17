/**
 * Shared dashboard state: the global filters, the freshness of the archive, and a ticking
 * clock for relative times. Every page reads from here; only the setters write.
 */

import { parseRangeSpec, type RangeSpec } from "./range";

const DEFAULT_RANGE: RangeSpec = { kind: "preset", preset: "30d" };
const STORAGE_KEY = "gate-cache.filters";
export const POLL_INTERVAL_MS = 2500;
/** Consecutive failed polls before the dashboard calls itself stale. */
export const STALE_AFTER_FAILURES = 2;

/** The browser's IANA time zone, which the API uses to bucket days. */
export function timeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

/** Return the current time in Unix seconds. */
export function nowSeconds(): number {
  return Date.now() / 1000;
}

export interface Filters {
  /** Git common directories of the selected repos, with `-` for the unknown repo; empty for every repo. */
  repos: string[];
  range: RangeSpec;
}

/**
 * Return the filters stored as JSON in `raw`, falling back to the defaults for anything
 * missing or malformed. The older `{repo, range}` shape with one repo and a bare preset loads too.
 */
export function parseStoredFilters(raw: string | null): Filters {
  const fallback: Filters = { repos: [], range: DEFAULT_RANGE };
  if (!raw) return fallback;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return fallback;
  }
  if (typeof parsed !== "object" || parsed === null) return fallback;
  const { repos, repo, range } = parsed as Record<string, unknown>;
  const listed = Array.isArray(repos) ? repos : typeof repo === "string" ? [repo] : [];
  const valid = listed.filter((r): r is string => typeof r === "string" && r !== "");
  return { repos: [...new Set(valid)], range: parseRangeSpec(range) ?? DEFAULT_RANGE };
}

function loadFilters(): Filters {
  try {
    return parseStoredFilters(localStorage.getItem(STORAGE_KEY));
  } catch {
    // Storage can be missing or blocked; the defaults still work.
    return parseStoredFilters(null);
  }
}

function saveFilters(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
  } catch {
    // Persistence is a convenience only.
  }
}

/** The global repo and range filters. Read freely; change them with the setters below. */
export const filters: Filters = $state(loadFilters());

/** Select repos by git common directory, with `-` for the unknown repo, or every repo with []. */
export function setRepos(repos: string[]): void {
  filters.repos = [...new Set(repos)];
  saveFilters();
}

/** Select a date range. */
export function setRange(spec: RangeSpec): void {
  filters.range = spec;
  saveFilters();
}

/** The archive freshness, refreshed by `startFreshnessPolling`. */
export interface FreshnessState {
  /** The archive's ingest count as of the last successful poll. */
  version: number;
  /**
   * Counts changes of `version`; queries refetch when it moves. The pages load before the first
   * poll answers, so an ingest can land between the two. The first successful poll therefore
   * bumps it once when the archive has had any ingest, which costs at most one extra fetch.
   */
  changes: number;
  /** Client time in Unix seconds of the last successful poll, or null before the first. */
  updatedAt: number | null;
  /** Server time in Unix seconds of the last ingest that added events. */
  lastIngest: number | null;
  /** Whether recording is on; null until the first poll answers. */
  recording: boolean | null;
  /** The latest background ingest failure, or null when ingest is healthy. */
  ingestError: string | null;
  /** Consecutive failed polls. */
  failures: number;
  /** True after `STALE_AFTER_FAILURES` failed polls in a row. */
  stale: boolean;
}

export const freshness: FreshnessState = $state({
  version: 0,
  changes: 0,
  updatedAt: null,
  lastIngest: null,
  recording: null,
  ingestError: null,
  failures: 0,
  stale: false,
});

/** The fields of the freshness API response the poller needs. */
export interface FreshnessReading {
  ingest_count: number;
  last_ingest: number | null;
  recording: boolean;
  ingest_error: string | null;
}

/**
 * Poll `fetchFreshness` now and every `POLL_INTERVAL_MS`, updating `freshness`.
 *
 * @returns A function that stops polling.
 */
export function startFreshnessPolling(
  fetchFreshness: (signal: AbortSignal) => Promise<FreshnessReading>,
): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let controller: AbortController | undefined;
  let stopped = false;

  async function poll(): Promise<void> {
    controller = new AbortController();
    const signal = controller.signal;
    // A hung request counts as a failure instead of blocking every later poll.
    const timeout = setTimeout(() => controller?.abort(), POLL_INTERVAL_MS * 2);
    try {
      const reading = await fetchFreshness(signal);
      const first = freshness.updatedAt === null;
      if (first ? reading.ingest_count > 0 : reading.ingest_count !== freshness.version) {
        freshness.changes += 1;
      }
      freshness.version = reading.ingest_count;
      freshness.lastIngest = reading.last_ingest;
      freshness.recording = reading.recording;
      freshness.ingestError = reading.ingest_error;
      freshness.updatedAt = nowSeconds();
      freshness.failures = 0;
    } catch {
      if (stopped) return;
      freshness.failures += 1;
    } finally {
      clearTimeout(timeout);
    }
    freshness.stale = freshness.failures >= STALE_AFTER_FAILURES;
    if (!stopped) timer = setTimeout(poll, POLL_INTERVAL_MS);
  }

  void poll();
  return () => {
    stopped = true;
    clearTimeout(timer);
    controller?.abort();
  };
}

/** A clock in Unix seconds that ticks once a second, for relative times. */
export const clock: { now: number } = $state({ now: nowSeconds() });

/** Start ticking `clock`; returns a function that stops it. */
export function startClock(): () => void {
  const id = setInterval(() => {
    clock.now = nowSeconds();
  }, 1000);
  return () => clearInterval(id);
}
