import { createRawSnippet } from "svelte";
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import DataTable from "./DataTable.svelte";

interface Row {
  name: string;
  runs: number;
}

const columns = [
  { key: "name", label: "Gate" },
  { key: "runs", label: "Runs", align: "right" as const, text: (r: Row) => `${r.runs} runs` },
];

describe("DataTable", () => {
  it("renders rows in the initial sort with aria-sort on the sorted header", () => {
    const { body } = render(DataTable<Row>, {
      props: {
        label: "Gates",
        rows: [
          { name: "lint", runs: 2 },
          { name: "test", runs: 9 },
        ],
        columns,
        rowKey: (r: Row) => r.name,
        sort: { key: "runs", direction: "desc" },
      },
    });
    expect(body.indexOf("test")).toBeLessThan(body.indexOf("lint"));
    expect(body).toContain("9 runs");
    expect(body).toContain('aria-sort="descending"');
    expect(body).toContain('class="right');
  });

  it("renders the empty snippet when there are no rows", () => {
    const { body } = render(DataTable<Row>, {
      props: {
        label: "Gates",
        rows: [],
        columns,
        rowKey: (r: Row) => r.name,
        empty: createRawSnippet(() => ({ render: () => "<p>Nothing here</p>" })),
      },
    });
    expect(body).toContain("Nothing here");
    expect(body).not.toContain("<tbody");
  });

  it("makes rows focusable only when they can be activated", () => {
    const rows = [{ name: "lint", runs: 1 }];
    const base = { label: "Gates", rows, columns, rowKey: (r: Row) => r.name };
    expect(render(DataTable<Row>, { props: base }).body).not.toContain("tabindex");
    const clickable = render(DataTable<Row>, { props: { ...base, onRowClick: () => {} } }).body;
    expect(clickable).toContain('tabindex="0"');
  });

  it("leaves rows that cannot be activated unfocusable and highlights the active row", () => {
    const rows = [
      { name: "lint", runs: 1 },
      { name: "test", runs: 2 },
    ];
    const { body } = render(DataTable<Row>, {
      props: {
        label: "Gates",
        rows,
        columns,
        rowKey: (r: Row) => r.name,
        onRowClick: () => {},
        canActivate: (r: Row) => r.name !== "lint",
        activeKey: "test",
      },
    });
    expect(body.match(/tabindex="0"/g)).toHaveLength(1);
    expect(body).toContain('data-key="lint"');
    expect(body).toMatch(/data-key="test"[^>]*class="[^"]*active/);
  });
});
