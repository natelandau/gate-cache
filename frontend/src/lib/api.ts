/**
 * Typed fetchers for the dashboard JSON API under `/api/v1/`.
 *
 * Every fetcher except `getFreshness` scopes its query with the global filters unless the
 * caller passes an explicit `scope` or `repos`. Failures throw `ApiError`.
 */

import type { DayBucket } from "./fill";
import type { FreshnessReading } from "./state.svelte";
import { resolveRange } from "./range";
import { UNKNOWN_REPO } from "./router.svelte";
import { filters, nowSeconds, timeZone } from "./state.svelte";

export type { DayBucket };

/** An event outcome as recorded by gate-cache. */
export type Outcome = "skip" | "pass" | "pass_unrecorded" | "fail" | "uncached";

export interface Summary {
  /** Seconds saved by skips that had a known duration. */
  time_saved: number;
  /** Skips whose saved time is unknown, so they add nothing to `time_saved`. */
  unknown_saved_skips: number;
  /** Every recorded event, including uncached runs. */
  runs: number;
  skips: number;
  /** Skips over skips, passes, and fails; null when nothing ran. */
  skip_rate: number | null;
  uncached: number;
  failures: number;
  flaky_gates: number;
  /** Event counts per outcome. */
  outcomes: Record<Outcome, number>;
  /**
   * Totals for the window of equal length just before this one, or null when the range has no
   * start or that window reaches past retention or the first recorded event.
   */
  previous: PreviousTotals | null;
  /** Days with at least one event, in order. Gaps are not filled. */
  daily: DayBucket[];
}

export interface PreviousTotals {
  time_saved: number;
  runs: number;
  skips: number;
  skip_rate: number | null;
  failures: number;
  flaky_gates: number;
  /** Length of the previous window in days. */
  days: number;
}

/** Activity in one hour of the week, in the query's time zone. */
export interface HourCell {
  /** 0 is Sunday. */
  weekday: number;
  /** 0 to 23. */
  hour: number;
  runs: number;
  /** Seconds saved by skips. */
  saved: number;
  failures: number;
}

/** How often gates ran without the cache for one reason. */
export interface ReasonRow {
  outcome: "uncached" | "pass_unrecorded";
  reason: string;
  count: number;
}

/** A gate whose median passing run time grew since the previous window. */
export interface SlowdownRow {
  repo: string | null;
  repo_name: string;
  name: string;
  /** Median passing run time in seconds in the previous window. */
  before: number;
  /** Median passing run time in seconds in this window. */
  now: number;
  /** Relative growth, such as 0.25 for 25% slower. */
  change: number;
}

export interface Slowdowns {
  gates: SlowdownRow[];
  /** False when no previous window exists to compare against. */
  comparable: boolean;
}

export interface GateRow {
  repo: string | null;
  repo_name: string;
  name: string;
  runs: number;
  skip_rate: number | null;
  avg_run: number | null;
  median_run: number | null;
  time_saved: number;
  failures: number;
  last_run: number;
  flaky: boolean;
}

export interface EventRow {
  ts: number;
  repo: string | null;
  repo_name: string;
  name: string;
  outcome: Outcome;
  duration: number | null;
  saved: number | null;
  exit_code: number | null;
  reason: string | null;
  tree: string | null;
  /** True when the run reported the failure of the run it waited for, without running. */
  reported: boolean;
}

export interface FlakyTree {
  tree: string;
  fails: number;
  passes: number;
  last: number;
}

export interface GateDetail {
  repo: string | null;
  repo_name: string;
  name: string;
  /** Duration of each pass, oldest first. */
  trend: { ts: number; duration: number }[];
  /** Newest events first, at most 50. */
  recent: EventRow[];
  flaky_trees: FlakyTree[];
}

export interface RepoRow {
  repo: string | null;
  repo_name: string;
  runs: number;
  skip_rate: number | null;
  time_saved: number;
  failures: number;
  /** Distinct gate names. */
  gates: number;
}

export interface ActivityPage {
  events: EventRow[];
  /** Opaque cursor for the next page, or null on the last page. */
  next_before: string | null;
}

export interface FlakyGate {
  repo: string | null;
  repo_name: string;
  name: string;
  tree_count: number;
  last_seen: number;
  /** Each flaky tree with its runs, oldest first. */
  trees: { tree: string; runs: EventRow[] }[];
}

export type Freshness = FreshnessReading;

/** A failed API call. `status` is 0 when the server could not be reached. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** The repos, time range, and zone a query covers. */
export interface QueryScope {
  /** Git common directories, with `-` for the unknown repo; empty for every repo. */
  repos: string[];
  /** Inclusive lower bound in Unix seconds. */
  from?: number;
  /** Exclusive upper bound in Unix seconds. */
  to?: number;
  /** IANA zone used to bucket days. */
  tz: string;
}

/** Options every fetcher accepts. */
export interface RequestOptions {
  signal?: AbortSignal;
  /** Overrides the scope derived from the global filters. */
  scope?: QueryScope;
  /**
   * Overrides the scope's repos, such as a gate's own repo; an empty list selects every repo.
   * The range and zone still come from the scope, and the repo filter is not read.
   */
  repos?: string[];
}

/**
 * Return the scope the global filters select at `now`, with `repos` in place of the repo filter
 * when given. The repo filter is read only without `repos`, so a reactive caller that passes
 * them does not reload on a filter change.
 */
export function currentScope(now: number = nowSeconds(), repos?: string[]): QueryScope {
  return {
    repos: repos ?? [...filters.repos],
    ...resolveRange(filters.range, new Date(now * 1000)),
    tz: timeZone(),
  };
}

type Params = Record<string, string | number | string[] | null | undefined>;

function scopeParams(scope: QueryScope): Params {
  return { repo: scope.repos, from: scope.from, to: scope.to, tz: scope.tz };
}

/**
 * Return the path and query string for an endpoint. A list value repeats its key once per
 * entry, and null and undefined values are dropped.
 */
export function apiUrl(endpoint: string, params: Params = {}): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) {
      for (const item of value) query.append(key, item);
    } else if (value !== null && value !== undefined) {
      query.set(key, String(value));
    }
  }
  const text = query.toString();
  return `/api/v1/${endpoint}${text ? `?${text}` : ""}`;
}

async function request<T>(endpoint: string, params: Params, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(endpoint, params), {
      signal,
      headers: { Accept: "application/json" },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Could not reach the dashboard server.", 0);
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError(`The server sent an unreadable response (HTTP ${response.status}).`, response.status);
  }
  if (!response.ok) {
    const message =
      typeof body === "object" && body !== null && typeof (body as { error?: unknown }).error === "string"
        ? (body as { error: string }).error
        : `HTTP ${response.status}`;
    throw new ApiError(message, response.status);
  }
  return body as T;
}

function scoped(options: RequestOptions): Params {
  const scope = options.scope ?? currentScope(undefined, options.repos);
  return scopeParams(options.repos === undefined ? scope : { ...scope, repos: options.repos });
}

export function getSummary(options: RequestOptions = {}): Promise<Summary> {
  return request("summary", scoped(options), options.signal);
}

export async function getGates(options: RequestOptions = {}): Promise<GateRow[]> {
  const body = await request<{ gates: GateRow[] }>("gates", scoped(options), options.signal);
  return body.gates;
}

/**
 * Fetch one gate's detail. `repo` is the gate's own repo, not the global filter; null selects
 * events recorded without a repo. The range still follows the global filters.
 */
export function getGate(
  name: string,
  repo: string | null,
  options: RequestOptions = {},
): Promise<GateDetail> {
  const params = { ...scoped({ ...options, repos: [repo ?? UNKNOWN_REPO] }), name };
  return request("gate", params, options.signal);
}

export async function getRepos(options: RequestOptions = {}): Promise<RepoRow[]> {
  const body = await request<{ repos: RepoRow[] }>("repos", scoped(options), options.signal);
  return body.repos;
}

/**
 * Fetch one page of events, newest first. Pass the previous page's `next_before` to continue,
 * an `outcome` to keep only events with that outcome, and a `reason` to keep only events
 * recorded with that reason.
 */
export function getActivity(
  page: { limit?: number; before?: string | null; outcome?: Outcome; reason?: string } = {},
  options: RequestOptions = {},
): Promise<ActivityPage> {
  const params = {
    ...scoped(options),
    limit: page.limit,
    before: page.before,
    outcome: page.outcome,
    reason: page.reason,
  };
  return request("activity", params, options.signal);
}

export async function getFlaky(options: RequestOptions = {}): Promise<FlakyGate[]> {
  const body = await request<{ gates: FlakyGate[] }>("flaky", scoped(options), options.signal);
  return body.gates;
}

/** Fetch activity for each of the 168 hours of the week, Sunday first. */
export async function getHourly(options: RequestOptions = {}): Promise<HourCell[]> {
  const body = await request<{ cells: HourCell[] }>("hourly", scoped(options), options.signal);
  return body.cells;
}

/** Fetch why gates ran without the cache, most common first. */
export async function getReasons(options: RequestOptions = {}): Promise<ReasonRow[]> {
  const body = await request<{ reasons: ReasonRow[] }>("reasons", scoped(options), options.signal);
  return body.reasons;
}

/** Fetch the gates whose run time grew most since the previous window. */
export function getSlowdowns(options: RequestOptions = {}): Promise<Slowdowns> {
  return request("slowdowns", scoped(options), options.signal);
}

export function getFreshness(options: { signal?: AbortSignal } = {}): Promise<Freshness> {
  return request("freshness", {}, options.signal);
}
