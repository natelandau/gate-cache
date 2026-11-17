/**
 * Shared dashboard state: the global filters, the freshness of the archive, and a ticking
 * clock for relative times. Every page reads from here; only the setters write.
 */

export type Range = "24h" | "7d" | "30d" | "90d" | "all";

/** The range presets in display order. */
export const RANGES: readonly { value: Range; label: string; long: string }[] = [
  { value: "24h", label: "24h", long: "Last 24 hours" },
  { value: "7d", label: "7d", long: "Last 7 days" },
  { value: "30d", label: "30d", long: "Last 30 days" },
  { value: "90d", label: "90d", long: "Last 90 days" },
  { value: "all", label: "All", long: "All time" },
];

const RANGE_SECONDS: Record<Exclude<Range, "all">, number> = {
  "24h": 86400,
  "7d": 7 * 86400,
  "30d": 30 * 86400,
  "90d": 90 * 86400,
};

const DEFAULT_RANGE: Range = "30d";
const STORAGE_KEY = "gate-cache.filters";
export const POLL_INTERVAL_MS = 2500;
/** Consecutive failed polls before the dashboard calls itself stale. */
export const STALE_AFTER_FAILURES = 2;

/** Return whether `value` is a known range preset. */
export function isRange(value: unknown): value is Range {
  return typeof value === "string" && RANGES.some((range) => range.value === value);
}

/**
 * Return the API bounds for a range preset, in Unix seconds.
 *
 * Ranges end at the present, so only `from` is set; `all` sets neither.
 */
export function rangeBounds(range: Range, now: number): { from?: number; to?: number } {
  return range === "all" ? {} : { from: now - RANGE_SECONDS[range] };
}

/** The browser's IANA time zone, which the API uses to bucket days. */
export function timeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

/** Return the current time in Unix seconds. */
export function nowSeconds(): number {
  return Date.now() / 1000;
}

export interface Filters {
  /** Git common directory of the selected repo, or null for every repo. */
  repo: string | null;
  range: Range;
}

function loadFilters(): Filters {
  const fallback: Filters = { repo: null, range: DEFAULT_RANGE };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return fallback;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return fallback;
    const { repo, range } = parsed as Record<string, unknown>;
    return {
      repo: typeof repo === "string" && repo !== "" ? repo : null,
      range: isRange(range) ? range : DEFAULT_RANGE,
    };
  } catch {
    // Storage can be missing or blocked; the defaults still work.
    return fallback;
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

/** Select one repo by its git common directory, or every repo with null. */
export function setRepo(repo: string | null): void {
  filters.repo = repo;
  saveFilters();
}

/** Select a range preset. */
export function setRange(range: Range): void {
  filters.range = range;
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
