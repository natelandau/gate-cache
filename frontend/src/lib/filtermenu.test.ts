import { describe, expect, it } from "vitest";
import type { ActivityFilter } from "./api";
import {
  gateChoices,
  groupChoices,
  listValues,
  MENU_SECTIONS,
  pickerEntry,
  reasonChoices,
  withList,
  withToggle,
} from "./filtermenu";

const lint = { repo: "/a/.git", repo_name: "a", name: "lint" };

describe("MENU_SECTIONS", () => {
  it("offers every pickable filter exactly once, with a picker for all but the toggles", () => {
    const kinds = MENU_SECTIONS.flatMap((section) => section.entries.map((entry) => entry.kind));
    expect(kinds.sort()).toEqual(["flaky", "gate", "group", "outcome", "reason", "span", "spotCheck"]);
    expect(pickerEntry("flaky")).toBeUndefined();
    expect(pickerEntry("gate")?.kind).toBe("gate");
  });
});

describe("gateChoices", () => {
  it("names gates by repo only when they span repos, and keeps applied gates the list lacks", () => {
    expect(gateChoices([lint]).map((c) => c.label)).toEqual(["lint"]);
    const choices = gateChoices([{ ...lint, name: "test" }, { ...lint, repo: "/b/.git", repo_name: "b" }], [
      { repo: null, name: "old" },
      { repo: "/b/.git", name: "lint" },
    ]);
    expect(choices.map((c) => c.label)).toEqual(["old", "lint (b)", "test (a)"]);
    expect(choices[1]?.item).toEqual({ repo: "/b/.git", name: "lint" });
  });
});

describe("reasonChoices", () => {
  it("lists a reason once even when it comes with two outcomes", () => {
    const rows = [{ reason: "dirty tree" }, { reason: "dirty tree" }, { reason: "cache off" }];
    expect(reasonChoices(rows).map((c) => c.value)).toEqual(["cache off", "dirty tree"]);
  });
});

describe("groupChoices", () => {
  it("builds the same group a Breakdown link applies, and keeps an applied group of the same dimension", () => {
    const applied = { by: "branch" as const, key: "gone", label: "Branch: gone" };
    const choices = groupChoices("branch", [{ key: "k1", label: "main" }], applied);
    expect(choices.map((c) => c.item)).toEqual([applied, { by: "branch", key: "k1", label: "Branch: main" }]);
    expect(groupChoices("machine", [{ key: "m", label: "box" }], applied)).toHaveLength(1);
  });
});

describe("withList and withToggle", () => {
  it("set a filter's values, and remove the filter when none are left", () => {
    const start: ActivityFilter = { outcome: ["fail"], flaky: true };
    expect(withList(start, "outcome", ["fail", "skip"])).toEqual({ outcome: ["fail", "skip"], flaky: true });
    expect(withList(start, "outcome", [])).toEqual({ flaky: true });
    expect(withToggle(start, "flaky", false)).toEqual({ outcome: ["fail"] });
    expect(withToggle(start, "spotCheck", true)).toEqual({ outcome: ["fail"], flaky: true, spotCheck: true });
  });

  it("check the applied gates in their picker", () => {
    const gate = { repo: null, name: "lint" };
    const [choice] = gateChoices([{ repo: null, repo_name: "unknown repo", name: "lint" }]);
    expect(listValues({ gate: [gate] }, "gate")).toEqual([choice?.value]);
  });
});
