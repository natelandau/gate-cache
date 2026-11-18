/** Column definitions and sorting for DataTable. */

import type { Snippet } from "svelte";

export type SortDirection = "asc" | "desc";

export interface SortState<K extends string = string> {
  key: K;
  direction: SortDirection;
}

/**
 * Return the sort after a header click: the sorted column flips direction, and another column
 * starts at `first`, which is usually descending for numbers and ascending for names.
 */
export function nextSort<K extends string>(sort: SortState<K> | null, key: K, first: SortDirection): SortState<K> {
  if (sort?.key === key) return { key, direction: sort.direction === "asc" ? "desc" : "asc" };
  return { key, direction: first };
}

/** Return the `aria-sort` value of the column `key` under `sort`. */
export function ariaSort(sort: SortState | null | undefined, key: string): "ascending" | "descending" | undefined {
  if (sort?.key !== key) return undefined;
  return sort.direction === "asc" ? "ascending" : "descending";
}

export interface Column<T> {
  /** Unique column id; also the row property read when no accessor is given. */
  key: string;
  label: string;
  /** Right-align numbers so digits line up. Defaults to left. */
  align?: "left" | "right";
  /** Defaults to true. */
  sortable?: boolean;
  /** Value to sort by. Defaults to `row[key]`. */
  sortValue?: (row: T) => string | number | null;
  /** Cell text. Defaults to `String(row[key])`, with null shown as an en space. */
  text?: (row: T) => string;
  /** Custom cell content; takes precedence over `text`. */
  cell?: Snippet<[T]>;
  /** What the column measures, shown in an info tip beside the header. */
  info?: string;
  /** Hover text for the cell, such as a full path behind a short name. */
  title?: (row: T) => string | undefined;
  /** CSS width of the column, such as "120px" or "40%". */
  width?: string;
  /** The first sort direction when the header is clicked. Defaults to desc for right-aligned. */
  firstDirection?: SortDirection;
}

/** Read the property `key` of a row. */
export function raw<T>(row: T, key: string): unknown {
  return (row as Record<string, unknown>)[key];
}

/** Return `rows` sorted by `sort`, nulls last, stable. */
export function sortRows<T>(rows: T[], columns: Column<T>[], sort: SortState | null): T[] {
  const column = sort && columns.find((c) => c.key === sort.key);
  if (!sort || !column) return rows;
  const value = column.sortValue ?? ((row: T) => raw(row, column.key) as string | number | null);
  const factor = sort.direction === "asc" ? 1 : -1;
  return rows
    .map((row, index) => ({ row, index, v: value(row) }))
    .sort((a, b) => {
      const aNull = a.v === null || a.v === undefined;
      const bNull = b.v === null || b.v === undefined;
      if (aNull || bNull) return aNull === bNull ? a.index - b.index : aNull ? 1 : -1;
      const order =
        typeof a.v === "number" && typeof b.v === "number"
          ? a.v - b.v
          : String(a.v).localeCompare(String(b.v), undefined, { numeric: true });
      return order === 0 ? a.index - b.index : order * factor;
    })
    .map((item) => item.row);
}
