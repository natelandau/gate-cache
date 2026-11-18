import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { BreakdownRow } from "../api";
import { breakdownBars } from "../breakdown";
import BarList from "./BarList.svelte";

function repo(path: string | null, name: string, time_saved: number): BreakdownRow {
  return {
    key: JSON.stringify([path]),
    label: name,
    title: path,
    missing: path === null,
    repo: path,
    name: null,
    runs: 1,
    skip_rate: null,
    time_saved,
    failures: 0,
    gates: 1,
  };
}

const rows = [repo("/w/api/.git", "api", 200), repo(null, "unknown repo", 50)];

describe("BarList", () => {
  it("scales bars to the largest value and shows the heading, columns, and titles", () => {
    const { body } = render(BarList<BreakdownRow>, {
      props: {
        label: "Repos",
        heading: "Branch",
        rows: breakdownBars(rows, "saved", "repo", []),
        color: "saved",
        columns: [{ label: "Gates", text: (row: BreakdownRow) => `${row.gates} gates` }],
        onpick: () => {},
      },
    });
    expect(body).toMatch(/<th scope="col"[^>]*>Branch<\/th>/);
    expect(body).toMatch(/width: 100%;[^"]*background: var\(--chart-saved\)/);
    expect(body).toMatch(/width: 25%;[^"]*background: var\(--chart-saved\)/);
    expect(body).toContain("1 gates");
    expect(body).toContain('title="/w/api/.git"');
  });

  it("mutes dimmed rows, marks them not selected, and draws their bar in the neutral color", () => {
    const { body } = render(BarList<BreakdownRow>, {
      props: {
        label: "Repos",
        heading: "Repo",
        rows: breakdownBars(rows, "saved", "repo", ["-"]),
        color: "fails",
        columns: [],
        onpick: () => {},
      },
    });
    expect(body.match(/class="[^"]*\bdimmed\b/g)).toHaveLength(1);
    expect(body.match(/\(not selected\)/g)).toHaveLength(1);
    expect(body).toMatch(/api(<!--[^>]*-->)*<span[^>]*class="visually-hidden[^"]*"[^>]*> \(not selected\)/);
    expect(body).toMatch(/width: 100%;[^"]*background: var\(--chart-neutral\)/);
    expect(body).toMatch(/width: 25%;[^"]*background: var\(--chart-failures\)/);
  });
});
