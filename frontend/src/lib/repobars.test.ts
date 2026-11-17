import { describe, expect, it } from "vitest";
import type { RepoRow } from "./api";
import { repoBars } from "./repobars";

function repo(path: string | null, name: string, overrides: Partial<RepoRow> = {}): RepoRow {
  return {
    repo: path,
    repo_name: name,
    runs: 0,
    skip_rate: null,
    time_saved: 0,
    failures: 0,
    gates: 1,
    ...overrides,
  };
}

const rows = [
  repo("/w/api/.git", "api", { time_saved: 500, runs: 10, skip_rate: 0.5, failures: 1 }),
  repo("/w/web/.git", "web", { time_saved: 90, runs: 40, skip_rate: 0.8, failures: 4 }),
  repo(null, "unknown repo", { time_saved: 30, runs: 25, skip_rate: null, failures: 2 }),
];

const labels = (bars: ReturnType<typeof repoBars>) => bars.map((bar) => bar.label);

describe("repoBars", () => {
  it("sorts by time saved", () => {
    const bars = repoBars(rows, "saved", []);
    expect(labels(bars)).toEqual(["api", "web", "unknown repo"]);
    expect(bars.map((bar) => bar.value)).toEqual([500, 90, 30]);
  });

  it("sorts by runs", () => {
    expect(labels(repoBars(rows, "runs", []))).toEqual(["web", "unknown repo", "api"]);
  });

  it("sorts by skip rate, with no rate as zero", () => {
    const bars = repoBars(rows, "skip", []);
    expect(labels(bars)).toEqual(["web", "api", "unknown repo"]);
    expect(bars.at(-1)?.value).toBe(0);
  });

  it("sorts by failures", () => {
    expect(labels(repoBars(rows, "fails", []))).toEqual(["web", "unknown repo", "api"]);
  });

  it("keys the unknown repo as - and keeps the source row", () => {
    const bars = repoBars(rows, "saved", []);
    expect(bars.map((bar) => bar.key)).toEqual(["/w/api/.git", "/w/web/.git", "-"]);
    expect(bars[0]?.row).toBe(rows[0]);
  });

  it("dims every repo outside the selection", () => {
    const bars = repoBars(rows, "saved", ["-"]);
    expect(bars.map((bar) => [bar.label, bar.dimmed])).toEqual([
      ["api", true],
      ["web", true],
      ["unknown repo", false],
    ]);
  });

  it("dims nothing when every repo is selected", () => {
    expect(repoBars(rows, "saved", []).some((bar) => bar.dimmed)).toBe(false);
  });
});
