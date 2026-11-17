/**
 * Typed fetchers for the dashboard JSON API under `/api/v1/`.
 *
 * Every fetcher except `getFreshness` scopes its query with the global filters unless the
 * caller passes an explicit `scope` or `repo`. Failures throw `ApiError`.
 */

import type { DayBucket } from "./fill";
import type { FreshnessReading } from "./state.svelte";
import { filters, nowSeconds, rangeBounds, timeZone } from "./state.svelte";

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
  /** Days with at least one event, in order. Gaps are not filled. */
  daily: DayBucket[];
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

/** The repo, time range, and zone a query covers. */
export interface QueryScope {
  /** Git common directory, or null for every repo. */
  repo: string | null;
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
   * Overrides the scope's repo, such as a detail page's own repo; null drops the repo
   * parameter. The range and zone still come from the scope.
   */
  repo?: string | null;
}

/** Return the scope the global filters select at `now`. */
export function currentScope(now: number = nowSeconds()): QueryScope {
  return { repo: filters.repo, ...rangeBounds(filters.range, now), tz: timeZone() };
}

type Params = Record<string, string | number | null | undefined>;

function scopeParams(scope: QueryScope): Params {
  return { repo: scope.repo, from: scope.from, to: scope.to, tz: scope.tz };
}

/** Return the path and query string for an endpoint, dropping null and undefined values. */
export function apiUrl(endpoint: string, params: Params = {}): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined) query.set(key, String(value));
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
  const scope = options.scope ?? currentScope();
  return scopeParams(options.repo === undefined ? scope : { ...scope, repo: options.repo });
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
  return request("gate", { ...scoped({ ...options, repo }), name }, options.signal);
}

export async function getRepos(options: RequestOptions = {}): Promise<RepoRow[]> {
  const body = await request<{ repos: RepoRow[] }>("repos", scoped(options), options.signal);
  return body.repos;
}

/**
 * Fetch one page of events, newest first. Pass the previous page's `next_before` to continue,
 * and an `outcome` to keep only events with that outcome.
 */
export function getActivity(
  page: { limit?: number; before?: string | null; outcome?: Outcome } = {},
  options: RequestOptions = {},
): Promise<ActivityPage> {
  const params = { ...scoped(options), limit: page.limit, before: page.before, outcome: page.outcome };
  return request("activity", params, options.signal);
}

export async function getFlaky(options: RequestOptions = {}): Promise<FlakyGate[]> {
  const body = await request<{ gates: FlakyGate[] }>("flaky", scoped(options), options.signal);
  return body.gates;
}

export function getFreshness(options: { signal?: AbortSignal } = {}): Promise<Freshness> {
  return request("freshness", {}, options.signal);
}
