import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiUrl,
  getActivity,
  getGate,
  getGates,
  getHourly,
  getReasons,
  getSlowdowns,
  getSummary,
  getTriage,
} from "./api";

const scope = { repos: ["/work/app/.git"], from: 100, tz: "Europe/Paris" };

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

  it("repeats a parameter once per list entry", () => {
    expect(apiUrl("gates", { repo: ["a", "-"] })).toContain("repo=a&repo=-");
    expect(apiUrl("gates", { repo: [], tz: "UTC" })).toBe("/api/v1/gates?tz=UTC");
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

  it("send the gate's own repo, with - for the unknown repo", async () => {
    respond(200, {});
    await getGate("lint", null, { scope: { ...scope, repos: ["/a/.git", "/b/.git"] } });
    expect(calledUrl().searchParams.getAll("repo")).toEqual(["-"]);
    expect(calledUrl().searchParams.get("name")).toBe("lint");
    expect(calledUrl().searchParams.get("from")).toBe("100");
  });

  it("send a known gate repo as the only repo", async () => {
    respond(200, {});
    await getGate("lint", "/work/other/.git", { scope });
    expect(calledUrl().searchParams.getAll("repo")).toEqual(["/work/other/.git"]);
  });

  it("send explicit repos in place of the scope's repos", async () => {
    respond(200, { daily: [] });
    await getSummary({ scope, repos: ["/work/other/.git", "-"] });
    expect(calledUrl().searchParams.getAll("repo")).toEqual(["/work/other/.git", "-"]);
    expect(calledUrl().searchParams.get("from")).toBe("100");
  });

  it("drop the repo when the override is empty", async () => {
    respond(200, { gates: [] });
    await getGates({ scope, repos: [] });
    expect(calledUrl().searchParams.has("repo")).toBe(false);
  });

  it("send the activity outcome, reason, limit, and repo override", async () => {
    respond(200, { events: [], next_before: null });
    await getActivity(
      { limit: 20, outcome: ["uncached", "fail"], reason: ["dirty tree"] },
      { scope, repos: ["/work/other/.git"] },
    );
    const params = calledUrl().searchParams;
    expect(params.getAll("outcome")).toEqual(["uncached", "fail"]);
    expect(params.get("reason")).toBe("dirty tree");
    expect(params.get("limit")).toBe("20");
    expect(params.getAll("repo")).toEqual(["/work/other/.git"]);
  });

  it("send the activity gate, and flaky filters", async () => {
    respond(200, { events: [], next_before: null });
    const gate = [
      { repo: null, name: "lint" },
      { repo: "/r/.git", name: "test" },
    ];
    await getActivity({ gate, flaky: true }, { scope });
    const params = calledUrl().searchParams;
    expect(params.getAll("gate")).toEqual(["-\0lint", "/r/.git\0test"]);
    expect(params.get("flaky")).toBe("1");
  });

  it("send the triage reason only when one is picked", async () => {
    respond(200, { items: [] });
    await getTriage({ scope, reason: "flaky" });
    expect(calledUrl().searchParams.get("reason")).toBe("flaky");
    vi.unstubAllGlobals();
    respond(200, { items: [] });
    await getTriage({ scope });
    expect(calledUrl().searchParams.has("reason")).toBe(false);
  });

  it("unwrap the hourly cells and the reasons", async () => {
    const cell = { weekday: 0, hour: 9, runs: 2, saved: 1.5, failures: 0 };
    respond(200, { cells: [cell] });
    expect(await getHourly({ scope })).toEqual([cell]);
    expect(calledUrl().pathname).toBe("/api/v1/hourly");
    vi.unstubAllGlobals();
    const reason = { outcome: "uncached", reason: "dirty tree", count: 3 };
    respond(200, { reasons: [reason] });
    expect(await getReasons({ scope })).toEqual([reason]);
    expect(calledUrl().pathname).toBe("/api/v1/reasons");
  });

  it("return slowdowns with whether a comparison exists", async () => {
    const body = { gates: [], comparable: false };
    respond(200, body);
    expect(await getSlowdowns({ scope })).toEqual(body);
    expect(calledUrl().pathname).toBe("/api/v1/slowdowns");
    expect(calledUrl().searchParams.getAll("repo")).toEqual(["/work/app/.git"]);
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
