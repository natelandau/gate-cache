import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiUrl, getActivity, getGate, getGates, getSummary } from "./api";

const scope = { repo: "/work/app/.git", from: 100, tz: "Europe/Paris" };

function respond(status: number, body: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

function calledUrl(): URL {
  const fetchMock = vi.mocked(fetch);
  return new URL(String(fetchMock.mock.calls[0]?.[0]), "http://127.0.0.1");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiUrl", () => {
  it("drops null and undefined parameters", () => {
    expect(apiUrl("summary", { repo: null, from: 5, to: undefined, tz: "UTC" })).toBe(
      "/api/v1/summary?from=5&tz=UTC",
    );
    expect(apiUrl("freshness")).toBe("/api/v1/freshness");
  });
});

describe("fetchers", () => {
  it("send the scope as query parameters", async () => {
    respond(200, { daily: [] });
    await getSummary({ scope });
    const url = calledUrl();
    expect(url.pathname).toBe("/api/v1/summary");
    expect(url.searchParams.get("repo")).toBe("/work/app/.git");
    expect(url.searchParams.get("from")).toBe("100");
    expect(url.searchParams.has("to")).toBe(false);
    expect(url.searchParams.get("tz")).toBe("Europe/Paris");
  });

  it("send the gate's own repo, and omit it for the unknown repo", async () => {
    respond(200, {});
    await getGate("lint", null, { scope });
    expect(calledUrl().searchParams.has("repo")).toBe(false);
    expect(calledUrl().searchParams.get("name")).toBe("lint");
  });

  it("send an explicit repo in place of the scope's repo", async () => {
    respond(200, { daily: [] });
    await getSummary({ scope, repo: "/work/other/.git" });
    expect(calledUrl().searchParams.get("repo")).toBe("/work/other/.git");
    expect(calledUrl().searchParams.get("from")).toBe("100");
  });

  it("drop the repo when the override is null", async () => {
    respond(200, { gates: [] });
    await getGates({ scope, repo: null });
    expect(calledUrl().searchParams.has("repo")).toBe(false);
  });

  it("send the activity outcome, limit, and repo override", async () => {
    respond(200, { events: [], next_before: null });
    await getActivity({ limit: 20, outcome: "fail" }, { scope, repo: "/work/other/.git" });
    const params = calledUrl().searchParams;
    expect(params.get("outcome")).toBe("fail");
    expect(params.get("limit")).toBe("20");
    expect(params.get("repo")).toBe("/work/other/.git");
  });

  it("throw the server's error message with the status", async () => {
    respond(400, { error: "unknown time zone: 'Mars/Base'" });
    const failure = getSummary({ scope });
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({
      status: 400,
      message: "unknown time zone: 'Mars/Base'",
    });
  });

  it("throw a status 0 error when the server is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );
    await expect(getSummary({ scope })).rejects.toMatchObject({ status: 0 });
  });
});
