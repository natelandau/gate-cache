import { describe, expect, it } from "vitest";
import { repoLabel, repoOptions } from "./repos";

describe("repoOptions", () => {
  it("labels by name, sorted, and skips the unknown repo", () => {
    const out = repoOptions([
      { repo: "/w/zeta/.git", repo_name: "zeta" },
      { repo: null, repo_name: "unknown repo" },
      { repo: "/w/alpha/.git", repo_name: "alpha" },
    ]);
    expect(out).toEqual([
      { value: "/w/alpha/.git", label: "alpha", title: "/w/alpha/.git" },
      { value: "/w/zeta/.git", label: "zeta", title: "/w/zeta/.git" },
    ]);
  });

  it("adds the parent directory to repeated names", () => {
    const out = repoOptions([
      { repo: "/home/a/code/app/.git", repo_name: "app" },
      { repo: "/home/b/work/app/.git", repo_name: "app" },
    ]);
    expect(out.map((o) => o.label)).toEqual(["app (code)", "app (work)"]);
  });
});

describe("repoLabel", () => {
  const options = [{ value: "/w/app/.git", label: "app (w)", title: "/w/app/.git" }];

  it("uses the picker label", () => {
    expect(repoLabel("/w/app/.git", options)).toBe("app (w)");
  });

  it("falls back to the directory name, and null for all repos", () => {
    expect(repoLabel("/x/tool/.git", options)).toBe("tool");
    expect(repoLabel(null, options)).toBeNull();
  });
});
