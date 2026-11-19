import { describe, expect, it, vi } from "vitest";
import type { FlakyGate } from "../../lib/api";
import { html } from "../../lib/render.test-utils";
import { emptyTitle } from "../../lib/scope";
import { filters } from "../../lib/state.svelte";

const loaded = vi.hoisted(() => ({ data: undefined as unknown }));

vi.mock("../../lib/query.svelte", () => ({
  createQuery: () => ({ data: loaded.data, error: undefined, loading: false }),
}));

const { default: FlakyModule } = await import("./FlakyModule.svelte");

const gate: FlakyGate = {
  repo: "/work/app/.git",
  repo_name: "app",
  name: "test",
  tree_count: 0,
  last_seen: 1,
  trees: [],
  tests: [],
  retried: [{ name: "tests/test_net.py::test_fetch", runs: 4, last: 1 }],
};

describe("FlakyModule", () => {
  it("shows the empty state when the only gates have retried tests and no flaky tree", () => {
    loaded.data = { gates: [gate], tests_cutoff: null };
    const body = html(FlakyModule, { props: { repoLabel: null } });
    expect(body).toContain(emptyTitle("flaky gates", { range: filters.range, repoLabel: null }));
    expect(body).not.toContain("<table");
  });
});
