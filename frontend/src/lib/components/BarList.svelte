<!--
  @component
  A table of repos, each with a bar scaled to the largest value and compact numeric columns.
  The name is a button that picks the repo. The numeric columns are the text equivalent, so
  the bars are hidden from screen readers. Dimmed rows use muted text, a neutral bar, and a
  hidden "(not selected)" note after the name.

  Props:
  - `label`: accessible name of the table (rendered as a hidden caption)
  - `rows`: the bars, in display order, from `repoBars` in `src/lib/repobars.ts`
  - `color`: the bar color by role: time saved, runs, or failures
  - `columns`: the numeric columns after the bar, each with a header and its cell text
  - `onpick`: called with a row's key when its name is clicked
-->
<script lang="ts">
  import type { RepoRow } from "../api";
  import type { RepoBar } from "../repobars";

  interface Props {
    label: string;
    rows: RepoBar[];
    color: "saved" | "runs" | "fails";
    columns: { label: string; text: (row: RepoRow) => string }[];
    onpick: (key: string) => void;
  }

  let { label, rows, color, columns, onpick }: Props = $props();

  const FILLS = {
    saved: "var(--chart-saved)",
    runs: "var(--chart-runs)",
    fails: "var(--chart-failures)",
  };

  const max = $derived(Math.max(0, ...rows.map((row) => row.value)));

  function width(value: number): string {
    return max > 0 ? `${(value / max) * 100}%` : "0%";
  }
</script>

<div class="wrap">
  <table class="bars">
    <caption class="visually-hidden">{label}</caption>
    <thead>
      <tr>
        <th scope="col">Repo</th>
        <th class="bar-cell" aria-hidden="true"></th>
        {#each columns as column (column.label)}
          <th scope="col" class="num">{column.label}</th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each rows as bar (bar.key)}
        <tr class:dimmed={bar.dimmed}>
          <th scope="row" class="name">
            <button type="button" title={bar.row.repo ?? undefined} onclick={() => onpick(bar.key)}>
              {bar.label}{#if bar.dimmed}<span class="visually-hidden">{" (not selected)"}</span>{/if}
            </button>
          </th>
          <td class="bar-cell" aria-hidden="true">
            <div class="track">
              <div
                class="fill"
                style:width={width(bar.value)}
                style:background={bar.dimmed ? "var(--chart-neutral)" : FILLS[color]}
              ></div>
            </div>
          </td>
          {#each columns as column (column.label)}
            <td class="num mono">{column.text(bar.row)}</td>
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
    padding: 0 var(--space-2);
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
    text-align: left;
  }

  thead th {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-muted);
  }

  tbody tr:last-child > * {
    border-bottom: 0;
  }

  .num {
    text-align: right;
  }

  .name {
    width: 180px;
    max-width: 180px;
    overflow: hidden;
    text-overflow: ellipsis;
    font-weight: 400;
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
    width: 100%;
    min-width: 80px;
  }

  .track {
    height: 12px;
    border-radius: 2px;
    background: var(--surface-sunken);
    overflow: hidden;
  }

  .fill {
    height: 100%;
    border-radius: 2px;
  }

  .dimmed .name button,
  .dimmed td {
    color: var(--text-muted);
  }
</style>
