import { describe, expect, it } from "vitest";
import { repoLabel, repoOptions, repoSelectionLabel } from "./repos";

describe("repoOptions", () => {
  it("labels by name, sorted, with the unknown repo last", () => {
    const out = repoOptions([
      { repo: "/w/zeta/.git", repo_name: "zeta" },
      { repo: null, repo_name: "unknown repo" },
      { repo: "/w/alpha/.git", repo_name: "alpha" },
    ]);
    expect(out).toEqual([
      { value: "/w/alpha/.git", label: "alpha", title: "/w/alpha/.git" },
      { value: "/w/zeta/.git", label: "zeta", title: "/w/zeta/.git" },
      { value: "-", label: "unknown repo" },
    ]);
  });

  it("offers no unknown repo option when every event has a repo", () => {
    expect(repoOptions([{ repo: "/w/a/.git", repo_name: "a" }]).map((o) => o.value)).toEqual(["/w/a/.git"]);
  });
});

describe("repoLabel", () => {
  const options = [{ value: "/w/app/.git", label: "app (w)", title: "/w/app/.git" }];

  it("uses the picker label", () => {
    expect(repoLabel("/w/app/.git", options)).toBe("app (w)");
  });

  it("falls back to the directory name", () => {
    expect(repoLabel("/x/tool/.git", options)).toBe("tool");
  });

  it("names the unknown repo as the API does when no option lists it", () => {
    expect(repoLabel("-", options)).toBe("unknown repo");
  });
});

describe("repoSelectionLabel", () => {
  const options = [
    { value: "/w/api-server/.git", label: "api-server", title: "/w/api-server/.git" },
    { value: "-", label: "unknown repo" },
  ];

  it("names one repo, counts several, and is null for all", () => {
    expect(repoSelectionLabel(["/w/api-server/.git"], options)).toBe("api-server");
    expect(repoSelectionLabel(["-"], options)).toBe("unknown repo");
    expect(repoSelectionLabel(["/w/api-server/.git", "-", "/x/tool/.git"], options)).toBe("3 repos");
    expect(repoSelectionLabel([], options)).toBeNull();
  });
});
