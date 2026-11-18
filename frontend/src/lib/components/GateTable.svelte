<!--
  @component
  The gates table on the Gates page. Rows open the gate panel.

  Props:
  - `rows`: the gates
  - `label`: accessible name of the table
  - `showRepo`: show the Repo column; off on a page about one repo
  - `sort`: bindable sort state, so a page keeps it across reloads
  - `activeKey`: the `gateKey` of the gate whose panel is open
  - `onRowClick`: open a gate
  - `busy`: dims the rows while newer data loads
  - `empty`: snippet shown when there are no gates
-->
<script lang="ts">
  import { TERMS } from "../terms";
  import type { Snippet } from "svelte";
  import type { GateRow } from "../api";
  import {
    formatBytes,
    formatCount,
    formatDuration,
    formatPercent,
    formatRatio,
    formatRelative,
    formatTimestamp,
  } from "../format";
  import { gateKey, splitGateName } from "../gates";
  import { clock } from "../state.svelte";
  import Badge from "./Badge.svelte";
  import DataTable, { type Column, type SortState } from "./DataTable.svelte";

  interface Props {
    rows: GateRow[];
    label: string;
    showRepo?: boolean;
    sort?: SortState | null;
    activeKey?: string | null;
    onRowClick: (gate: GateRow) => void;
    busy?: boolean;
    empty?: Snippet;
  }

  let {
    rows,
    label,
    showRepo = true,
    sort = $bindable({ key: "time_spent", direction: "desc" }),
    activeKey = null,
    onRowClick,
    busy = false,
    empty,
  }: Props = $props();

  const NOT_RECORDED = "not recorded";

  function notRecorded(value: number | null): string | undefined {
    return value === null ? NOT_RECORDED : undefined;
  }

  const repoColumn: Column<GateRow> = {
    key: "repo_name",
    label: "Repo",
    title: (g) => g.repo ?? "Recorded outside a git repo",
  };

  const columns = $derived<Column<GateRow>[]>([
    { key: "name", label: "Gate", cell: gateCell, title: (g) => g.name, firstDirection: "asc" },
    ...(showRepo ? [repoColumn] : []),
    {
      key: "runs",
      label: TERMS.calls.column,
      align: "right",
      text: (g) => formatCount(g.runs),
      info: "Every time the gate was called, whether its command ran or the cache skipped it.",
    },
    {
      key: "skip_rate",
      label: TERMS.skipRate.column,
      align: "right",
      text: (g) => formatPercent(g.skip_rate),
      info: "The share of calls that checked the cache and were skipped because the gate already passed on the same content.",
    },
    {
      key: "avg_run",
      label: "Avg run",
      align: "right",
      text: (g) => formatDuration(g.avg_run),
      info: "Mean run time of the gate's passing runs.",
    },
    {
      key: "time_spent",
      label: TERMS.ran.column,
      align: "right",
      text: (g) => formatDuration(g.time_spent),
      info: "Total time the gate's command ran, failed runs included. Skipped calls take no time.",
    },
    {
      key: "median_run",
      label: "Median run",
      align: "right",
      text: (g) => formatDuration(g.median_run),
      title: (g) => notRecorded(g.median_run),
      info: "The middle run time of the gate's passing runs: half ran faster, half slower.",
    },
    {
      key: "p90_run",
      label: "p90 run",
      align: "right",
      text: (g) => formatDuration(g.p90_run),
      title: (g) => notRecorded(g.p90_run),
      info: "90th percentile run time of the gate's passing runs: 9 in 10 finished this fast or faster. Needs at least 5 passes.",
    },
    {
      key: "cpu_ratio",
      label: "CPU/wall",
      align: "right",
      text: (g) => formatRatio(g.cpu_ratio),
      title: (g) =>
        notRecorded(g.cpu_ratio) ?? "CPU seconds per wall second. Near 1× means the gate uses one core.",
      info: "CPU time divided by run time. Near 1× means the gate keeps one core busy; above 1× means it runs in parallel; well below 1× means it mostly waits, such as on the network or disk.",
    },
    {
      key: "peak_rss",
      label: "Peak memory",
      align: "right",
      text: (g) => formatBytes(g.peak_rss),
      title: (g) =>
        notRecorded(g.peak_rss) ?? (g.median_rss === null ? undefined : `Median ${formatBytes(g.median_rss)}`),
      info: "The most memory any single run of the gate used at once. Hover a value for the median across runs.",
    },
    {
      key: "time_saved",
      label: TERMS.saved.column,
      align: "right",
      text: (g) => formatDuration(g.time_saved),
      info: "Run time that skipped calls did not spend, taken from the passing run that let each one skip.",
    },
    { key: "failures", label: "Failures", align: "right", cell: failuresCell },
    {
      key: "fail_time",
      label: "Lost to failures",
      align: "right",
      text: (g) => formatDuration(g.fail_time),
      info: "The part of time ran that went to runs that failed.",
    },
    {
      key: "last_run",
      label: "Last run",
      align: "right",
      text: (g) => formatRelative(g.last_run, clock.now),
      title: (g) => formatTimestamp(g.last_run),
    },
  ]);
</script>

{#snippet gateCell(g: GateRow)}
  {@const parts = splitGateName(g.name)}
  <span class="gate">
    <span class="name">{parts.base}{#if parts.suffix}<span class="suffix">{parts.suffix}</span>{/if}</span>
    {#if g.flaky}<Badge tone="flaky" title="A tree both failed and passed in this range">flaky</Badge>{/if}
  </span>
{/snippet}

{#snippet failuresCell(g: GateRow)}
  <span class:danger={g.failures > 0}>{formatCount(g.failures)}</span>
{/snippet}

<DataTable
  {label}
  {rows}
  {columns}
  bind:sort
  rowKey={gateKey}
  {activeKey}
  {onRowClick}
  rowLabel={(g) => (showRepo ? `Open ${g.name} in ${g.repo_name}` : `Open ${g.name}`)}
  {busy}
  {empty}
/>

<style>
  /* Long names, such as a full command line, wrap instead of widening the column, so every
     character stays readable and the other columns stay in view. */
  .gate {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: 6px 0;
    font-weight: 500;
    line-height: 18px;
    white-space: normal;
  }

  /* As wide as the name, up to 240px; a longer name wraps at that width and never squeezes
     narrower, so the column holds its size when the table scrolls. */
  .name {
    flex: none;
    width: max-content;
    max-width: 240px;
    overflow-wrap: anywhere;
  }

  .suffix {
    color: var(--text-faint);
    font-weight: 400;
  }

  .danger {
    color: var(--danger);
  }
</style>
