import { beforeEach, describe, expect, it, vi } from "vitest";
import type { GateDetail as Detail } from "../lib/api";
import { html } from "../lib/render.test-utils";
import { reportProblemText } from "../lib/tests";

const loaded = vi.hoisted(() => ({ data: undefined as unknown }));

vi.mock("../lib/query.svelte", () => ({
  createQuery: () => ({ data: loaded.data, error: undefined, loading: false }),
}));

const { default: GateDetail, TEST_DETAIL_DOCS_URL, TESTS_CUTOFF_NOTE } = await import("./GateDetail.svelte");

const base: Detail = {
  repo: "/work/app/.git",
  repo_name: "app",
  name: "test",
  histogram: null,
  failure_timing: {
    threshold: null,
    early: { runs: 0, time: 0 },
    late: { runs: 0, time: 0 },
    unclassified: { runs: 0, time: 0 },
  },
  by_source: [],
  trend: [{ ts: 1, duration: 100 }],
  recent: [
    {
      ts: 1,
      repo: "/work/app/.git",
      repo_name: "app",
      gate: "test",
      name: "test",
      outcome: "pass",
      duration: 100,
      saved: null,
      reason: null,
      tree: "abc",
      reported: false,
    } as Detail["recent"][number],
  ],
  flaky_trees: [],
  slowest_tests: [],
  has_tests: true,
  report_problems: { missing: 0, stale: 0, invalid: 0 },
  tests_cutoff: null,
};

/** Return the table row that names `test`, so a value can be matched within that row only. */
function rowOf(body: string, test: string): string {
  const name = test.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return body.match(new RegExp(`<tr[^>]*>(?:(?!</tr>)[\\s\\S])*${name}[\\s\\S]*?</tr>`))?.[0] ?? "";
}

function render(detail: Partial<Detail>): string {
  loaded.data = { detail: { ...base, ...detail }, row: undefined };
  return html(GateDetail, { props: { repo: base.repo, name: base.name, onclose: () => {} } });
}

describe("GateDetail tests", () => {
  beforeEach(() => {
    loaded.data = undefined;
  });

  it("lists the slowest tests with their median durations", () => {
    const body = render({
      slowest_tests: [
        { name: "tests/test_api.py::test_sync", median: 94, runs: 12, share: 0.5 },
        { name: "tests/test_cli.py::test_help", median: 3, runs: 12, share: null },
      ],
    });
    expect(rowOf(body, "test_api.py::test_sync")).toMatch(/>\s*1m 34s\s*</);
    expect(rowOf(body, "test_cli.py::test_help")).toMatch(/>\s*3s\s*</);
  });

  it("links to the test detail docs when the gate has no test reports", () => {
    expect(render({ has_tests: false })).toContain(`href="${TEST_DETAIL_DOCS_URL}"`);
    expect(render({ has_tests: true })).not.toContain(`href="${TEST_DETAIL_DOCS_URL}"`);
  });

  it("warns when recent runs had report problems", () => {
    const report_problems = { missing: 0, stale: 2, invalid: 0 };
    expect(render({ report_problems })).toContain(reportProblemText(report_problems));
  });

  it("shows the report problem instead of the --junit hint", () => {
    const body = render({ has_tests: false, report_problems: { missing: 3, stale: 0, invalid: 0 } });
    expect(body).toContain(reportProblemText({ missing: 3, stale: 0, invalid: 0 }));
    expect(body).not.toContain(`href="${TEST_DETAIL_DOCS_URL}"`);
  });

  it("notes that per-test figures stop at the retention cutoff", () => {
    expect(render({ tests_cutoff: 1_700_000_000 })).toContain(TESTS_CUTOFF_NOTE);
    expect(render({ tests_cutoff: null })).not.toContain(TESTS_CUTOFF_NOTE);
  });
});
