import { describe, expect, it } from "vitest";
import { href, openerAfter, parseHash, repoPageRepo, type Route } from "./router.svelte";

describe("parseHash", () => {
  it("defaults to the overview", () => {
    expect(parseHash("")).toEqual({ page: "overview" });
    expect(parseHash("#/")).toEqual({ page: "overview" });
    expect(parseHash("#/nope")).toEqual({ page: "overview" });
    expect(parseHash("#/repos/a/b")).toEqual({ page: "overview" });
    expect(parseHash("#/repos/")).toEqual({ page: "overview" });
    expect(parseHash("#/flaky/extra")).toEqual({ page: "overview" });
  });

  it("parses the simple pages", () => {
    for (const page of ["overview", "gates", "repos", "activity", "flaky"]) {
      expect(parseHash(`#/${page}`)).toEqual({ page });
    }
  });

  it("parses a gate route", () => {
    expect(parseHash("#/gates/%2Fwork%2Fapp%2F.git/lint%2Fstrict")).toEqual({
      page: "gate",
      repo: "/work/app/.git",
      name: "lint/strict",
    });
    expect(parseHash("#/gates/-/test")).toEqual({ page: "gate", repo: null, name: "test" });
  });

  it("parses a repo route", () => {
    expect(parseHash("#/repos/%2Fwork%2Fapp%2F.git")).toEqual({
      page: "repo",
      repo: "/work/app/.git",
    });
  });

  it("falls back on malformed encoding", () => {
    expect(parseHash("#/gates/%E0%A4%A/test")).toEqual({ page: "overview" });
    expect(parseHash("#/repos/%E0%A4%A")).toEqual({ page: "overview" });
  });
});

describe("href", () => {
  it("round-trips through parseHash", () => {
    const routes: Route[] = [
      { page: "overview" },
      { page: "flaky" },
      { page: "gate", repo: "/a b/.git", name: "ruff check #1" },
      { page: "gate", repo: null, name: "test" },
      { page: "repo", repo: "/a b/#x/.git" },
    ];
    for (const route of routes) expect(parseHash(href(route))).toEqual(route);
  });
});

describe("openerAfter", () => {
  const gates: Route = { page: "gates" };
  const activity: Route = { page: "activity" };
  const lint: Route = { page: "gate", repo: null, name: "lint" };
  const test: Route = { page: "gate", repo: null, name: "test" };

  it("records the page a gate was opened from", () => {
    expect(openerAfter(activity, lint, null)).toEqual(activity);
  });

  it("keeps the opener when the panel switches gates and clears it on leaving", () => {
    expect(openerAfter(lint, test, gates, true)).toEqual(gates);
    expect(openerAfter(lint, gates, gates)).toBeNull();
    expect(openerAfter(lint, gates, gates, true)).toBeNull();
  });

  it("drops the opener when the gate changes outside the panel", () => {
    expect(openerAfter(lint, test, gates)).toBeNull();
  });

  it("has no opener when the app loads on a gate", () => {
    expect(openerAfter(null, lint, null)).toBeNull();
  });
});

describe("repoPageRepo", () => {
  const repo: Route = { page: "repo", repo: "/work/app/.git" };
  const lint: Route = { page: "gate", repo: null, name: "lint" };

  it("returns the repo of a repo page", () => {
    expect(repoPageRepo(repo, null)).toBe("/work/app/.git");
  });

  it("keeps the repo page under a gate opened from it", () => {
    expect(repoPageRepo(lint, repo)).toBe("/work/app/.git");
  });

  it("returns null elsewhere", () => {
    expect(repoPageRepo(lint, { page: "gates" })).toBeNull();
    expect(repoPageRepo(lint, null)).toBeNull();
    expect(repoPageRepo({ page: "repos" }, null)).toBeNull();
  });
});
