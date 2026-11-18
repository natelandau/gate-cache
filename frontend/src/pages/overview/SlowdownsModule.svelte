<!--
  @component
  Gates getting slower: the gates whose median passing run time grew most since the previous
  period of the same length, with both medians and the change. A row opens the gate's detail
  panel.

  Props:
  - `repoLabel`: the repo selection's display name, or null for all repos
  - `span`: page-local days the overview is scoped to, if any
-->
<script lang="ts">
  import Icon from "../../lib/components/Icon.svelte";
  import Badge from "../../lib/components/Badge.svelte";
  import { getSlowdowns, spanScope, type SlowdownRow } from "../../lib/api";
  import DataTable, { type Column } from "../../lib/components/DataTable.svelte";
  import Module from "../../lib/components/Module.svelte";
  import { formatDuration, formatPercent } from "../../lib/format";
  import { gateKey } from "../../lib/gates";
  import { openGatePanel } from "../../lib/panel";
  import { createQuery } from "../../lib/query.svelte";
  import { emptyTitle } from "../../lib/scope";
  import type { DaySpan } from "../../lib/selection";
  import { filters } from "../../lib/state.svelte";

  interface Props {
    repoLabel: string | null;
    /** Page-local days the overview is scoped to. */
    span?: DaySpan;
  }

  let { repoLabel, span }: Props = $props();

  // Matches the server's `min_runs` for slowdowns.
  const MIN_RUNS = 5;

  const query = createQuery(
    (signal) => getSlowdowns({ signal, scope: spanScope(span) }),
    () => span,
  );

  const comparable = $derived(query.data?.comparable ?? true);
  const rows = $derived(query.data?.gates ?? []);

  const columns: Column<SlowdownRow>[] = [
    { key: "name", label: "Gate", sortable: false, cell: gate },
    {
      key: "before",
      label: "Median before",
      align: "right",
      sortable: false,
      text: (g) => formatDuration(g.before),
    },
    { key: "now", label: "Now", align: "right", sortable: false, text: (g) => formatDuration(g.now) },
    { key: "change", label: "Change", align: "right", sortable: false, cell: change },
  ];
</script>

{#snippet gate(g: SlowdownRow)}
  {g.name} <span class="repo" title={g.repo ?? undefined}>{g.repo_name}</span>
{/snippet}
{#snippet change(g: SlowdownRow)}
  <Badge tone="danger"
    ><Icon name="trending-up" size={12} /><span class="visually-hidden">Up</span>&nbsp;{formatPercent(g.change)}</Badge
  >
{/snippet}

<Module
  title="Gates getting slower"
  titleId="slowdowns-title"
  noun="slowdowns"
  loading={query.loading && !query.data}
  error={query.error}
  empty={!query.data || !comparable || rows.length === 0}
  emptyTitle={comparable
    ? emptyTitle("slower gates", { range: filters.range, span, repoLabel })
    : "No previous period to compare against."}
  emptyDetail={comparable
    ? `Only gates with at least ${MIN_RUNS} passing runs in both periods are compared.`
    : "This needs a full previous period of the same length. All time, ranges longer than about six months, and ranges that start soon after stats were turned on have none."}
>
  <DataTable
    label="Gates getting slower"
    bare
    {rows}
    rowKey={gateKey}
    {columns}
    onRowClick={(g) => openGatePanel(g)}
    rowLabel={(g) => `Open ${g.name}`}
    busy={query.loading}
  />
  {#snippet footer()}
    <span>Gates with at least {MIN_RUNS} passing runs in both periods.</span>
  {/snippet}
</Module>

<style>
  .repo {
    color: var(--text-faint);
    font-size: var(--text-xs);
  }


</style>
