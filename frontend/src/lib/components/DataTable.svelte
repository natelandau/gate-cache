<!--
  @component
  A dense, sortable table with optional row activation.

  Props:
  - `rows`: the data
  - `columns`: column definitions, see `Column` below
  - `rowKey`: a stable unique key per row
  - `label`: accessible name of the table (rendered as a hidden caption)
  - `sort`: initial sort `{ key, direction }`; bindable to read or drive it from outside
  - `onRowClick`: makes rows focusable and activatable with click, Enter, or Space
  - `rowLabel`: accessible description of what activating a row does, such as "Open lint"
  - `canActivate`: rows for which it returns false are neither focusable nor clickable
  - `activeKey`: the `rowKey` of a row to highlight, such as the one a detail panel shows
  - `empty`: snippet shown in place of the body when `rows` is empty
  - `busy`: dims the rows while newer data loads
  - `bare`: drops the outer border and background, for a table inside a panel such as `Module`

  Each row carries `data-key` with its `rowKey`, so a page can return focus to it.

  Sorting compares `sortValue(row)` (or the raw `row[key]`), places null last in both
  directions, and is stable, so equal rows keep their incoming order.

  Example:

  ```svelte
  <DataTable
    label="Gates"
    rows={gates}
    rowKey={(g) => `${g.repo}:${g.name}`}
    columns={[
      { key: "name", label: "Gate" },
      { key: "runs", label: "Runs", align: "right", text: (g) => formatCount(g.runs) },
    ]}
    onRowClick={(g) => navigate({ page: "gate", repo: g.repo, name: g.name })}
  >
    {#snippet empty()}<EmptyState title="No gates in this range" />{/snippet}
  </DataTable>
  ```
-->
<script lang="ts" module>
  export type { Column, SortDirection, SortState } from "../table";
</script>

<script lang="ts" generics="T">
  import type { Snippet } from "svelte";
  import { raw, sortRows, type Column, type SortState } from "../table";

  interface Props {
    rows: T[];
    columns: Column<T>[];
    rowKey: (row: T) => string;
    label: string;
    sort?: SortState | null;
    onRowClick?: (row: T) => void;
    rowLabel?: (row: T) => string;
    canActivate?: (row: T) => boolean;
    activeKey?: string | null;
    empty?: Snippet;
    busy?: boolean;
    bare?: boolean;
  }

  let {
    rows,
    columns,
    rowKey,
    label,
    sort = $bindable(null),
    onRowClick,
    rowLabel,
    canActivate = () => true,
    activeKey = null,
    empty,
    busy = false,
    bare = false,
  }: Props = $props();

  const sorted = $derived(sortRows(rows, columns, sort));

  function toggle(column: Column<T>): void {
    if (sort?.key === column.key) {
      sort = { key: column.key, direction: sort.direction === "asc" ? "desc" : "asc" };
    } else {
      const first = column.firstDirection ?? (column.align === "right" ? "desc" : "asc");
      sort = { key: column.key, direction: first };
    }
  }

  function ariaSort(column: Column<T>): "ascending" | "descending" | undefined {
    if (sort?.key !== column.key) return undefined;
    return sort.direction === "asc" ? "ascending" : "descending";
  }

  function cellText(row: T, column: Column<T>): string {
    if (column.text) return column.text(row);
    const value = raw(row, column.key);
    return value === null || value === undefined ? " " : String(value);
  }

  function isInteractive(target: EventTarget | null): boolean {
    return target instanceof Element && target.closest("a, button, input, select, textarea") !== null;
  }

  function activate(event: MouseEvent | KeyboardEvent, row: T): void {
    if (!onRowClick || !canActivate(row) || isInteractive(event.target)) return;
    if (event instanceof KeyboardEvent) {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
    }
    onRowClick(row);
  }
</script>

<div class="table-wrap" class:bare aria-busy={busy}>
  <table class:busy>
    <caption class="visually-hidden">{label}</caption>
    <colgroup>
      {#each columns as column (column.key)}
        <col style:width={column.width} />
      {/each}
    </colgroup>
    <thead>
      <tr>
        {#each columns as column (column.key)}
          <th scope="col" class={column.align ?? "left"} aria-sort={ariaSort(column)}>
            {#if column.sortable ?? true}
              <button type="button" onclick={() => toggle(column)}>
                <span>{column.label}</span>
                <span class="arrow" aria-hidden="true">
                  {#if sort?.key === column.key}{sort.direction === "asc" ? "↑" : "↓"}{/if}
                </span>
              </button>
            {:else}
              {column.label}
            {/if}
          </th>
        {/each}
      </tr>
    </thead>
    {#if sorted.length > 0}
      <tbody>
        {#each sorted as row (rowKey(row))}
          {@const live = !!onRowClick && canActivate(row)}
          <tr
            data-key={rowKey(row)}
            class:live
            class:active={activeKey !== null && rowKey(row) === activeKey}
            tabindex={live ? 0 : undefined}
            aria-label={live && rowLabel ? rowLabel(row) : undefined}
            onclick={(event) => activate(event, row)}
            onkeydown={(event) => activate(event, row)}
          >
            {#each columns as column (column.key)}
              <td class={column.align ?? "left"} title={column.title?.(row)}>
                {#if column.cell}
                  {@render column.cell(row)}
                {:else}
                  {cellText(row, column)}
                {/if}
              </td>
            {/each}
          </tr>
        {/each}
      </tbody>
    {/if}
  </table>
  {#if sorted.length === 0 && empty}
    {@render empty()}
  {/if}
</div>

<style>
  .table-wrap {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    overflow-x: auto;
  }

  .table-wrap.bare {
    border: 0;
    border-radius: 0;
    background: none;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    table-layout: auto;
    font-variant-numeric: tabular-nums;
  }

  th,
  td {
    height: var(--row-height);
    padding: 0 var(--space-3);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 420px;
  }

  th {
    background: var(--surface-sunken);
    border-bottom: 1px solid var(--border);
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-muted);
    text-align: left;
  }

  .right {
    text-align: right;
  }

  th button {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    height: 22px;
    margin: 0 -4px;
    padding: 0 4px;
    border: 0;
    border-radius: 3px;
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  th.right button {
    flex-direction: row-reverse;
  }

  th button:hover {
    color: var(--text);
  }

  .arrow {
    display: inline-block;
    width: 1ch;
    color: var(--accent);
  }

  td {
    border-top: 1px solid var(--border);
  }

  tbody tr:first-child td {
    border-top: 0;
  }

  tr.live {
    cursor: pointer;
  }

  tr.live:hover,
  tr.live:focus-visible {
    background: var(--surface-hover);
  }

  tr.active,
  tr.active:hover {
    background: var(--accent-soft);
    box-shadow: inset 2px 0 0 var(--accent);
  }

  tbody tr:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: -2px;
  }

  .busy tbody {
    opacity: 0.55;
  }
</style>
