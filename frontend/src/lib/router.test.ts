import { afterEach, describe, expect, it, vi } from "vitest";
import {
  href,
  openerAfter,
  panelHost,
  parseHash,
  router,
  startRouter,
  type Route,
} from "./router.svelte";
import { filters } from "./state.svelte";

describe("parseHash", () => {
  it("defaults to the overview", () => {
    expect(parseHash("")).toEqual({ page: "overview" });
    expect(parseHash("#/")).toEqual({ page: "overview" });
    expect(parseHash("#/nope")).toEqual({ page: "overview" });
    expect(parseHash("#/repos")).toEqual({ page: "overview" });
    expect(parseHash("#/repos/a/b")).toEqual({ page: "overview" });
    expect(parseHash("#/repos/")).toEqual({ page: "overview" });
    expect(parseHash("#/flaky/extra")).toEqual({ page: "overview" });
  });

  it("parses the simple pages", () => {
    for (const page of ["overview", "gates", "activity", "flaky"]) {
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

  it("turns an old repo route into a repo selection on the overview", () => {
    expect(parseHash("#/repos/%2Fx%2F.git")).toEqual({ page: "overview", selectRepo: "/x/.git" });
    expect(parseHash("#/repos/-")).toEqual({ page: "overview", selectRepo: "-" });
  });

  it("parses the activity filters", () => {
    expect(parseHash("#/activity?outcome=fail&reason=x%20y")).toEqual({
      page: "activity",
      outcome: "fail",
      reason: "x y",
    });
    expect(parseHash("#/activity?outcome=fail")).toEqual({ page: "activity", outcome: "fail" });
  });

  it("drops an unknown outcome and an empty reason", () => {
    expect(parseHash("#/activity?outcome=nope&reason=")).toEqual({ page: "activity" });
    expect(parseHash("#/activity?outcome=toString")).toEqual({ page: "activity" });
    expect(parseHash("#/activity?")).toEqual({ page: "activity" });
  });

  it("ignores query parameters on other pages", () => {
    expect(parseHash("#/flaky?outcome=fail")).toEqual({ page: "flaky" });
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
      { page: "activity" },
      { page: "activity", outcome: "uncached", reason: "GATE_CACHE_DISABLE is set & 50% #1+2" },
    ];
    for (const route of routes) expect(parseHash(href(route))).toEqual(route);
  });

  it("encodes the activity filters", () => {
    expect(href({ page: "activity", outcome: "fail" })).toBe("#/activity?outcome=fail");
    expect(href({ page: "activity", reason: "x y" })).toBe("#/activity?reason=x%20y");
    expect(href({ page: "activity" })).toBe("#/activity");
  });

  it("links the overview without a repo selection", () => {
    expect(href({ page: "overview", selectRepo: "/x/.git" })).toBe("#/overview");
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

describe("panelHost", () => {
  const lint: Route = { page: "gate", repo: null, name: "lint" };

  it("hosts a gate opened from the overview on the overview", () => {
    expect(panelHost(lint, { page: "overview" })).toBe("overview");
  });

  it("hosts any other gate on the Gates page", () => {
    expect(panelHost(lint, { page: "gates" })).toBe("gates");
    expect(panelHost(lint, { page: "activity" })).toBe("gates");
    expect(panelHost(lint, null)).toBe("gates");
  });

  it("has no host when no gate is open", () => {
    expect(panelHost({ page: "overview" }, null)).toBeNull();
    expect(panelHost({ page: "gates" }, { page: "overview" })).toBeNull();
  });
});

describe("startRouter", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("selects the repo of an old repo link and replaces the hash with the overview", () => {
    const replace = vi.fn();
    vi.stubGlobal("location", { hash: "#/repos/%2Fx%2F.git", replace });
    vi.stubGlobal("window", { addEventListener: vi.fn(), removeEventListener: vi.fn() });
    const stop = startRouter();
    expect(filters.repos).toEqual(["/x/.git"]);
    expect(replace).toHaveBeenCalledWith("#/overview");
    expect(router.route).toEqual({ page: "overview" });
    stop();
  });

  it("replaces a bare repos route with the overview and keeps the repo filter", () => {
    filters.repos = ["/kept/.git"];
    const replace = vi.fn();
    vi.stubGlobal("location", { hash: "#/repos", replace });
    vi.stubGlobal("window", { addEventListener: vi.fn(), removeEventListener: vi.fn() });
    const stop = startRouter();
    expect(replace).toHaveBeenCalledWith("#/overview");
    expect(filters.repos).toEqual(["/kept/.git"]);
    expect(router.route).toEqual({ page: "overview" });
    stop();
  });

  it("leaves a plain overview hash alone", () => {
    const replace = vi.fn();
    vi.stubGlobal("location", { hash: "#/overview", replace });
    vi.stubGlobal("window", { addEventListener: vi.fn(), removeEventListener: vi.fn() });
    const stop = startRouter();
    expect(replace).not.toHaveBeenCalled();
    stop();
  });
});
