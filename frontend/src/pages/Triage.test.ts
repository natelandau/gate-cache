import { describe, expect, it, vi } from "vitest";
import type { EventRow, FlakyItem, TriageItem } from "../lib/api";
import { html } from "../lib/render.test-utils";
import { TESTS_CUTOFF_NOTE } from "./GateDetail.svelte";
import Triage from "./Triage.svelte";
import { RETRIED_TITLE } from "./triage/FlakyEvidence.svelte";

const items: TriageItem[] = [];
const page = vi.hoisted(() => ({ items: [] as unknown[], tests_cutoff: null as number | null }));
// Noon UTC, so the run falls on the same local day in the test machine's zone.
const NOON = Date.UTC(2026, 10, 18, 12) / 1000;

vi.mock("../lib/query.svelte", () => ({
  createQuery: () => ({ data: page, error: undefined, loading: false }),
}));

function run(ts: number, outcome: EventRow["outcome"], spot_check: boolean): EventRow {
  return {
    ts,
    repo: "/r/.git",
    repo_name: "r",
    name: "lint",
    gate: "lint",
    outcome,
    duration: 1,
    saved: null,
    exit_code: outcome === "fail" ? 1 : 0,
    reason: null,
    tree: "abc123",
    reported: false,
    spot_check,
  };
}

items.push(
  {
    repo: "/r/.git",
    repo_name: "r",
    name: "lint",
    reason: "failed_spot_check",
    last_seen: NOON,
    evidence: { count: 1, runs: [run(NOON, "fail", true)] },
  },
  {
    repo: "/r/.git",
    repo_name: "r",
    name: "lint",
    reason: "flaky",
    last_seen: 20,
    evidence: {
      trees: [{ tree: "abc123", runs: [run(10, "fail", false), run(20, "pass", false)] }],
      tests: [],
      retried: [],
    },
  },
);

function render(rows: TriageItem[] = items, tests_cutoff: number | null = null): string {
  page.items = rows;
  page.tests_cutoff = tests_cutoff;
  return html(Triage, { props: { repoLabel: null, total: rows.length } });
}

const flakyGate: FlakyItem = {
  repo: "/work/app/.git",
  repo_name: "app",
  name: "test",
  reason: "flaky",
  last_seen: 1,
  evidence: { trees: [], tests: [], retried: [] },
};
const flakyTree = { tree: "abc123", runs: [] };
const flakyTest = { name: "tests/test_sync.py::test_merge", fails: 2, passes: 3, last: 1 };
const retriedTest = { name: "tests/test_net.py::test_fetch", runs: 4, last: 1 };

function withEvidence(evidence: Partial<FlakyItem["evidence"]>): FlakyItem {
  return { ...flakyGate, evidence: { ...flakyGate.evidence, ...evidence } };
}

function reasons(body: string): string[] {
  return [...body.matchAll(/data-reason="([^"]+)"/g)].map((m) => m[1]!);
}

describe("Triage", () => {
  it("lists one row per gate and reason", () => {
    expect(reasons(render())).toEqual(["failed_spot_check", "flaky"]);
  });

  it("links each failed spot check to that day's failed spot checks of the gate in Activity", () => {
    page.items = items;
    const body = html(Triage, { props: { repoLabel: null, reason: "failed_spot_check", total: 2 } });
    const link = body.match(/href="(#\/activity\?[^"]+)"/)?.[1] ?? "";
    const params = new URLSearchParams(link.replace(/&amp;/g, "&").split("?")[1]);
    expect(Object.fromEntries(params)).toMatchObject({
      outcome: "fail",
      gate: "/r/.git\0lint",
      spot_check: "1",
      from: "2026-11-18",
      to: "2026-11-18",
    });
  });

  it("lists a flaky gate's flaky tests under its trees", () => {
    const body = render([withEvidence({ trees: [flakyTree], tests: [flakyTest] })]);
    expect(body).toContain(flakyTest.name);
    expect(body).toContain("Runs on tree abc123");
    expect(body).not.toContain(RETRIED_TITLE);
  });

  it("shows tests that passed on retry in their own group, with no tree list", () => {
    const body = render([withEvidence({ retried: [retriedTest] })]);
    expect(body).toContain(RETRIED_TITLE);
    expect(body).toContain(retriedTest.name);
    expect(body).not.toContain("Runs on tree");
  });

  it("notes the per-test cutoff only when the range reaches past it and a gate lists tests", () => {
    const withTests = [withEvidence({ retried: [retriedTest] })];
    const treesOnly = [withEvidence({ trees: [flakyTree] })];
    expect(render(withTests, 1_700_000_000)).toContain(TESTS_CUTOFF_NOTE);
    expect(render(withTests, null)).not.toContain(TESTS_CUTOFF_NOTE);
    expect(render(treesOnly, 1_700_000_000)).not.toContain(TESTS_CUTOFF_NOTE);
  });
});
