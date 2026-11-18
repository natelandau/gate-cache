<!--
  @component
  A table of named rows, such as repos, each with a bar scaled to the largest value and compact
  numeric columns. The name is a button that picks the row. The numeric columns are the text
  equivalent, so the bars are hidden from screen readers. Dimmed rows use muted text, a neutral
  bar, and a hidden "(not selected)" note after the name.

  Props:
  - `label`: accessible name of the table (rendered as a hidden caption)
  - `heading`: header of the name column, such as "Repo"
  - `rows`: the bars, in display order, such as from `breakdownBars` in `src/lib/breakdown.ts`
  - `color`: the bar color by role: time saved, runs, or failures
  - `columns`: the numeric columns after the bar, each with a header and its cell text
  - `onpick`: called with a row's bar when its name is clicked
-->
<script lang="ts" module>
  import Meter from "./Meter.svelte";
  /** One row of a `BarList`. */
  export interface Bar<T> {
    /** Unique among the rows. */
    key: string;
    label: string;
    /** Hover text for the name. */
    title: string | undefined;
    value: number;
    /** True when a filter is active and leaves this row out. */
    dimmed: boolean;
    row: T;
  }
</script>

<script lang="ts" generics="T, K extends string">
  import { ariaSort, type SortState } from "../table";
  import SortHeader from "./SortHeader.svelte";

  interface Props {
    label: string;
    heading: string;
    rows: Bar<T>[];
    /** CSS color of the bars, such as "var(--chart-runs)". */
    color: string;
    columns: { key: K; label: string; text: (row: T) => string }[];
    onpick: (bar: Bar<T>) => void;
    /** The sorted column, "name" for the first column; with `onsort`, headers sort. */
    sort?: SortState<K | "name">;
    onsort?: (key: K | "name") => void;
    /** CSS widths of the name and bar columns; by default the bar takes the space the number columns leave. */
    widths?: { name?: string; bar?: string };
  }

  let { label, heading, rows, color, columns, onpick, sort, onsort, widths = {} }: Props = $props();

  const max = $derived(Math.max(0, ...rows.map((row) => row.value)));

  function share(value: number): number {
    return max > 0 ? value / max : 0;
  }
</script>

{#snippet header(key: K | "name", text: string, align: "left" | "right")}
  {#if onsort}
    <SortHeader label={text} direction={sort?.key === key ? sort.direction : null} {align} onclick={() => onsort(key)} />
  {:else}
    {text}
  {/if}
{/snippet}

<div class="wrap">
  <table class="bars">
    <caption class="visually-hidden">{label}</caption>
    <colgroup>
      <col style:width={widths.name} />
      <col style:width={widths.bar ?? "100%"} />
      {#each columns as column (column.key)}<col />{/each}
    </colgroup>
    <thead>
      <tr>
        <th scope="col" aria-sort={ariaSort(sort, "name")}>{@render header("name", heading, "left")}</th>
        <th class="bar-cell" aria-hidden="true"></th>
        {#each columns as column (column.key)}
          <th scope="col" class="num" aria-sort={ariaSort(sort, column.key)}>{@render header(column.key, column.label, "right")}</th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each rows as bar (bar.key)}
        <tr class:dimmed={bar.dimmed}>
          <th scope="row" class="name">
            <button type="button" title={bar.title} onclick={() => onpick(bar)}>
              {bar.label}{#if bar.dimmed}<span class="visually-hidden">{" (not selected)"}</span>{/if}
            </button>
          </th>
          <td class="bar-cell" aria-hidden="true">
            <Meter share={share(bar.value)} color={bar.dimmed ? "var(--chart-neutral)" : color} />
          </td>
          {#each columns as column (column.key)}
            <td class="num" class:sorted={sort?.key === column.key}>{column.text(bar.row)}</td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .wrap {
    overflow-x: auto;
  }

  .bars {
    width: 100%;
    border-collapse: collapse;
    font-variant-numeric: tabular-nums;
  }

  th,
  td {
    height: var(--row-height);
    padding: 0 10px;
    border-bottom: 1px solid var(--border-row);
    font-size: var(--text-sm);
    white-space: nowrap;
    text-align: left;
  }

  thead th {
    height: auto;
    vertical-align: bottom;
    border-bottom-color: var(--border);
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--text-muted);
  }

  th:first-child,
  td:first-child {
    padding-left: var(--space-1);
  }

  th:last-child,
  td:last-child {
    padding-right: var(--space-1);
  }

  tbody tr:last-child > * {
    border-bottom: 0;
  }

  .num {
    text-align: right;
  }

  .name {
    max-width: 240px;
    overflow: hidden;
    text-overflow: ellipsis;
    font-weight: 500;
  }

  .name button {
    max-width: 100%;
    padding: 0;
    overflow: hidden;
    border: 0;
    background: none;
    color: var(--text);
    font: inherit;
    text-align: left;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: pointer;
  }

  .name button:hover {
    text-decoration: underline;
  }

  .bar-cell {
    min-width: 48px;
  }

  .dimmed .name button,
  .dimmed td {
    color: var(--text-muted);
  }

  td.sorted {
    font-weight: 500;
  }
</style>
