<!--
  @component
  The gates table shared by the Gates page and the repo detail page. Rows open the gate panel.

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
  import type { Snippet } from "svelte";
  import type { GateRow } from "../api";
  import { formatCount, formatDuration, formatPercent, formatRelative, formatTimestamp } from "../format";
  import { gateKey } from "../gates";
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
    sort = $bindable({ key: "time_saved", direction: "desc" }),
    activeKey = null,
    onRowClick,
    busy = false,
    empty,
  }: Props = $props();

  const repoColumn: Column<GateRow> = {
    key: "repo_name",
    label: "Repo",
    title: (g) => g.repo ?? "Recorded outside a git repo",
  };

  const columns = $derived<Column<GateRow>[]>([
    { key: "name", label: "Gate", cell: gateCell, firstDirection: "asc" },
    ...(showRepo ? [repoColumn] : []),
    { key: "runs", label: "Runs", align: "right", text: (g) => formatCount(g.runs) },
    { key: "skip_rate", label: "Skip %", align: "right", text: (g) => formatPercent(g.skip_rate) },
    {
      key: "avg_run",
      label: "Avg run",
      align: "right",
      text: (g) => formatDuration(g.avg_run),
      title: (g) => (g.median_run === null ? undefined : `Median ${formatDuration(g.median_run)}`),
    },
    { key: "time_saved", label: "Saved", align: "right", text: (g) => formatDuration(g.time_saved) },
    { key: "failures", label: "Failures", align: "right", cell: failuresCell },
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
  <span class="gate">
    {g.name}
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
  .gate {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    font-weight: 500;
  }

  .danger {
    color: var(--danger);
  }
</style>
