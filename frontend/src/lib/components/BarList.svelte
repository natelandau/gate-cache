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

<script lang="ts" generics="T">
  import Icon from "./Icon.svelte";

  interface Props {
    label: string;
    heading: string;
    rows: Bar<T>[];
    color: "saved" | "runs" | "fails";
    columns: { key: string; label: string; text: (row: T) => string }[];
    onpick: (bar: Bar<T>) => void;
    /** The sorted column, "name" for the first column; with `onsort`, headers sort. */
    sort?: { key: string; direction: "asc" | "desc" };
    onsort?: (key: string) => void;
  }

  let { label, heading, rows, color, columns, onpick, sort, onsort }: Props = $props();

  function ariaSort(key: string): "ascending" | "descending" | undefined {
    if (sort?.key !== key) return undefined;
    return sort.direction === "asc" ? "ascending" : "descending";
  }

  const FILLS = {
    saved: "var(--chart-saved)",
    runs: "var(--chart-runs)",
    fails: "var(--chart-failures)",
  };

  const max = $derived(Math.max(0, ...rows.map((row) => row.value)));

  function share(value: number): number {
    return max > 0 ? value / max : 0;
  }
</script>

{#snippet header(key: string, text: string)}
  {#if onsort}
    <button type="button" class="sort" class:on={sort?.key === key} onclick={() => onsort(key)}>
      <span>{text}</span>
      <span class="arrow"
        >{#if sort?.key === key}<Icon name={sort.direction === "asc" ? "arrow-up" : "arrow-down"} size={12} />{/if}</span
      >
    </button>
  {:else}
    {text}
  {/if}
{/snippet}

<div class="wrap">
  <table class="bars">
    <caption class="visually-hidden">{label}</caption>
    <thead>
      <tr>
        <th scope="col" aria-sort={ariaSort("name")}>{@render header("name", heading)}</th>
        <th class="bar-cell" aria-hidden="true"></th>
        {#each columns as column (column.key)}
          <th scope="col" class="num" aria-sort={ariaSort(column.key)}>{@render header(column.key, column.label)}</th>
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
            <Meter share={share(bar.value)} color={bar.dimmed ? "var(--chart-neutral)" : FILLS[color]} />
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
    width: 160px;
    max-width: 160px;
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
    width: 24%;
    min-width: 48px;
  }


  .dimmed .name button,
  .dimmed td {
    color: var(--text-muted);
  }

  .sort {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    height: 22px;
    white-space: nowrap;
    margin: 0 -4px;
    padding: 0 4px;
    border: 0;
    border-radius: 3px;
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
    transition: color var(--dur-fast) var(--ease);
  }

  .num .sort {
    flex-direction: row-reverse;
  }

  .sort:hover,
  .sort.on {
    color: var(--text);
  }

  .arrow {
    display: inline-flex;
    width: 12px;
  }

  td.sorted {
    font-weight: 500;
  }
</style>
