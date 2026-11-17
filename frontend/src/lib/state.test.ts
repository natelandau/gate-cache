import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  freshness,
  parseStoredFilters,
  POLL_INTERVAL_MS,
  startFreshnessPolling,
} from "./state.svelte";

describe("parseStoredFilters", () => {
  const fallback = { repos: [], range: { kind: "preset", preset: "30d" } };

  it("migrates the old single-repo shape", () => {
    expect(parseStoredFilters('{"repo":"/x/.git","range":"7d"}')).toEqual({
      repos: ["/x/.git"],
      range: { kind: "preset", preset: "7d" },
    });
    expect(parseStoredFilters('{"repo":null,"range":"all"}')).toEqual({
      repos: [],
      range: { kind: "preset", preset: "all" },
    });
  });

  it("loads the current shape", () => {
    const stored = { repos: ["/a/.git", "-"], range: { kind: "period", period: "last_week" } };
    expect(parseStoredFilters(JSON.stringify(stored))).toEqual(stored);
  });

  it("drops bad entries and falls back to the defaults", () => {
    expect(parseStoredFilters(null)).toEqual(fallback);
    expect(parseStoredFilters("not json")).toEqual(fallback);
    expect(parseStoredFilters('"7d"')).toEqual(fallback);
    expect(parseStoredFilters('{"repos":["/a/.git","",3,"/a/.git"],"range":"2w"}')).toEqual({
      repos: ["/a/.git"],
      range: fallback.range,
    });
  });
});

describe("startFreshnessPolling", () => {
  const reading = { ingest_count: 3, last_ingest: 100, recording: true, ingest_error: null };

  beforeEach(() => {
    vi.useFakeTimers();
    Object.assign(freshness, {
      version: 0,
      changes: 0,
      failures: 0,
      stale: false,
      updatedAt: null,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("records a successful poll", async () => {
    const stop = startFreshnessPolling(async () => reading);
    await vi.advanceTimersByTimeAsync(0);
    expect(freshness.version).toBe(3);
    expect(freshness.recording).toBe(true);
    expect(freshness.updatedAt).not.toBeNull();
    expect(freshness.stale).toBe(false);
    stop();
  });

  it("turns stale after two failed polls and recovers on success", async () => {
    let fail = true;
    const stop = startFreshnessPolling(async () => {
      if (fail) throw new Error("down");
      return reading;
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(freshness.failures).toBe(1);
    expect(freshness.stale).toBe(false);
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    expect(freshness.stale).toBe(true);
    fail = false;
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    expect(freshness.stale).toBe(false);
    expect(freshness.failures).toBe(0);
    stop();
  });

  it("refetches once after the first poll, then on each count change", async () => {
    let count = 3;
    const stop = startFreshnessPolling(async () => ({ ...reading, ingest_count: count }));
    await vi.advanceTimersByTimeAsync(0);
    expect(freshness.version).toBe(3);
    expect(freshness.changes).toBe(1);
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    expect(freshness.changes).toBe(1);
    count = 4;
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    expect(freshness.version).toBe(4);
    expect(freshness.changes).toBe(2);
    stop();
  });

  it("does not refetch after the first poll of an archive with no ingests", async () => {
    const stop = startFreshnessPolling(async () => ({ ...reading, ingest_count: 0 }));
    await vi.advanceTimersByTimeAsync(0);
    expect(freshness.changes).toBe(0);
    stop();
  });

  it("stops polling when stopped", async () => {
    const fetcher = vi.fn(async () => reading);
    const stop = startFreshnessPolling(fetcher);
    await vi.advanceTimersByTimeAsync(0);
    stop();
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 4);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
