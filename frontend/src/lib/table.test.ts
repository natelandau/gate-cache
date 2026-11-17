import { describe, expect, it } from "vitest";
import { type Column, sortRows } from "./table";

interface Row {
  name: string;
  rate: number | null;
}

const rows: Row[] = [
  { name: "b", rate: 0.5 },
  { name: "a10", rate: null },
  { name: "a2", rate: 0.9 },
  { name: "c", rate: 0.5 },
];
const columns: Column<Row>[] = [
  { key: "name", label: "Name" },
  { key: "rate", label: "Rate", align: "right" },
  { key: "len", label: "Length", sortValue: (row) => row.name.length },
];
const names = (out: Row[]) => out.map((row) => row.name);

describe("sortRows", () => {
  it("keeps the incoming order without a sort", () => {
    expect(sortRows(rows, columns, null)).toBe(rows);
    expect(sortRows(rows, columns, { key: "missing", direction: "asc" })).toBe(rows);
  });

  it("sorts text naturally", () => {
    expect(names(sortRows(rows, columns, { key: "name", direction: "asc" }))).toEqual([
      "a2",
      "a10",
      "b",
      "c",
    ]);
  });

  it("puts nulls last in both directions and keeps ties stable", () => {
    expect(names(sortRows(rows, columns, { key: "rate", direction: "desc" }))).toEqual([
      "a2",
      "b",
      "c",
      "a10",
    ]);
    expect(names(sortRows(rows, columns, { key: "rate", direction: "asc" }))).toEqual([
      "b",
      "c",
      "a2",
      "a10",
    ]);
  });

  it("uses sortValue when given", () => {
    expect(names(sortRows(rows, columns, { key: "len", direction: "desc" }))).toEqual([
      "a10",
      "a2",
      "b",
      "c",
    ]);
  });
});
