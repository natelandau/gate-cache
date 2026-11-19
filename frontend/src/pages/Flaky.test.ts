import { describe, expect, it, vi } from "vitest";
import type { FlakyGate } from "../lib/api";
import { html } from "../lib/render.test-utils";

const loaded = vi.hoisted(() => ({ data: undefined as unknown }));

vi.mock("../lib/query.svelte", () => ({
  createQuery: () => ({ data: loaded.data, error: undefined, loading: false }),
}));

const { default: Flaky, RETRIED_TITLE } = await import("./Flaky.svelte");
const { TESTS_CUTOFF_NOTE } = await import("./GateDetail.svelte");

const gate: FlakyGate = {
  repo: "/work/app/.git",
  repo_name: "app",
  name: "test",
  tree_count: 0,
  last_seen: 1,
  trees: [],
  tests: [],
  retried: [],
};

const flakyTree = { tree: "abc123", runs: [] };
const flakyTest = { name: "tests/test_sync.py::test_merge", fails: 2, passes: 3, last: 1 };
const retriedTest = { name: "tests/test_net.py::test_fetch", runs: 4, last: 1 };

function render(gates: FlakyGate[], tests_cutoff: number | null = null): string {
  loaded.data = { gates, tests_cutoff };
  return html(Flaky, { props: { repoLabel: null } });
}

describe("Flaky tests", () => {
  it("lists a gate's flaky tests under it", () => {
    const body = render([{ ...gate, tree_count: 1, trees: [flakyTree], tests: [flakyTest] }]);
    expect(body).toContain(flakyTest.name);
    expect(body).toContain("Runs on tree abc123");
    expect(body).not.toContain(RETRIED_TITLE);
  });

  it("shows no tree list for a gate with no flaky tree", () => {
    const body = render([{ ...gate, tree_count: 0, trees: [], retried: [retriedTest] }]);
    expect(body).not.toContain("0 trees");
    expect(body).not.toContain("Runs on tree");
  });

  it("shows tests that passed on retry in their own group", () => {
    const body = render([{ ...gate, tree_count: 0, trees: [], retried: [retriedTest] }]);
    expect(body).toContain(RETRIED_TITLE);
    expect(body).toContain(retriedTest.name);
  });

  it("notes the per-test cutoff only when the range reaches past it and a gate lists tests", () => {
    const withTests = [{ ...gate, tree_count: 0, trees: [], retried: [retriedTest] }];
    const treesOnly = [{ ...gate, tree_count: 1, trees: [flakyTree] }];
    expect(render(withTests, 1_700_000_000)).toContain(TESTS_CUTOFF_NOTE);
    expect(render(withTests, null)).not.toContain(TESTS_CUTOFF_NOTE);
    expect(render(treesOnly, 1_700_000_000)).not.toContain(TESTS_CUTOFF_NOTE);
  });
});
