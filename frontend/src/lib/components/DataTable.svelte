<!--
  @component
  A dense, sortable table with optional row activation.

  Props:
  - `rows`: the data
  - `columns`: column definitions, see `Column` below; `info` adds an info tip to a header
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
  import { ariaSort, nextSort, raw, sortRows, type Column, type SortState } from "../table";
  import InfoTip from "./InfoTip.svelte";
  import SortHeader from "./SortHeader.svelte";

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

  // True once the table scrolls sideways, which shows the pinned first column's edge.
  let scrolled = $state(false);

  const sorted = $derived(sortRows(rows, columns, sort));

  function toggle(column: Column<T>): void {
    sort = nextSort(sort, column.key, column.firstDirection ?? (column.align === "right" ? "desc" : "asc"));
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

<div
  class="table-wrap"
  class:bare
  class:scrolled
  aria-busy={busy}
  onscroll={(event) => (scrolled = event.currentTarget.scrollLeft > 0)}
>
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
          <th scope="col" class="col-head {column.align ?? 'left'}" aria-sort={ariaSort(sort, column.key)}>
            {#snippet heading(describedby?: string)}
              {#if column.sortable ?? true}
                <SortHeader
                  label={column.label}
                  direction={sort?.key === column.key ? sort.direction : null}
                  align={column.align}
                  onclick={() => toggle(column)}
                  {describedby}
                />
              {:else}
                <span class:explained={!!describedby} aria-describedby={describedby}>{column.label}</span>
              {/if}
            {/snippet}
            <!-- One centered row, so a header with an explanation lines up with one without. Its
                 label opens the explanation on hover or focus; a dotted underline marks it. -->
            <span class="head">
              {#if column.info}
                <InfoTip text={column.info} label="About {column.label}">
                  {#snippet trigger(id)}{@render heading(id)}{/snippet}
                </InfoTip>
              {:else}
                {@render heading()}
              {/if}
            </span>
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
              {@const text = column.cell ? undefined : cellText(row, column)}
              <!-- A text cell can be cut by its ellipsis, so its title carries the full text. -->
              <td
                class={column.align === "right" ? "right num" : "left"}
                title={column.title ? column.title(row) : text}
              >
                {#if column.cell}
                  {@render column.cell(row)}
                {:else}
                  {text}
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
    border-radius: var(--radius-card);
    background: var(--surface);
    box-shadow: var(--ring);
    overflow-x: auto;
  }

  /* The first column stays in view while the rest of a wide table scrolls under it. Its cells
     need an opaque background, and row hover and the active row repaint it like any cell. */
  th:first-child,
  td:first-child {
    position: sticky;
    left: 0;
    z-index: 1;
    background: var(--surface);
  }

  th:first-child {
    z-index: 2;
  }

  .scrolled th:first-child,
  .scrolled td:first-child {
    box-shadow: inset -1px 0 0 var(--border);
  }

  .table-wrap.bare {
    border-radius: 0;
    background: none;
    box-shadow: none;
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
    padding: 0 10px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 420px;
  }

  .head {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    vertical-align: middle;
  }

  /* Headers never cut their text, and an info tip must show past the cell. */
  th {
    overflow: visible;
    height: 34px;
    border-bottom: 1px solid var(--border);
    text-align: left;
  }

  .bare th:first-child,
  .bare td:first-child {
    padding-left: var(--space-1);
  }

  .bare th:last-child,
  .bare td:last-child {
    padding-right: var(--space-1);
  }

  .right {
    text-align: right;
  }

  td {
    border-top: 1px solid var(--border-row);
    transition: background-color var(--dur-fast) var(--ease);
  }

  tbody tr:first-child td {
    border-top: 0;
  }

  tr.live {
    cursor: pointer;
  }

  tr.live:hover td,
  tr.live:focus-visible td {
    background: var(--surface-hover);
  }

  tr.active td,
  tr.active:hover td {
    background: var(--accent-soft);
  }

  tr.active td:first-child {
    box-shadow: inset 2px 0 0 var(--accent);
  }

  tbody tr:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: -2px;
  }

  .busy tbody {
    opacity: 0.55;
  }
  td {
    font-size: var(--text-sm);
  }
</style>
