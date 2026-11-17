<!--
  @component
  Flaky gates: the gates with the most flaky trees, each with a badge of its tree count. A
  row opens the gate's detail panel.

  Props:
  - `repoLabel`: the repo selection's display name, or null for all repos
-->
<script lang="ts">
  import { getFlaky, type FlakyGate } from "../../lib/api";
  import Badge from "../../lib/components/Badge.svelte";
  import DataTable from "../../lib/components/DataTable.svelte";
  import Module from "../../lib/components/Module.svelte";
  import { formatCount } from "../../lib/format";
  import { gateKey } from "../../lib/gates";
  import { openGatePanel } from "../../lib/panel";
  import { createQuery } from "../../lib/query.svelte";
  import { topFlaky } from "../../lib/rank";
  import { href } from "../../lib/router.svelte";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import { filters, freshness } from "../../lib/state.svelte";

  interface Props {
    repoLabel: string | null;
  }

  let { repoLabel }: Props = $props();

  const query = createQuery((signal) => getFlaky({ signal }));

  const rows = $derived(topFlaky(query.data ?? []));

  function treeText(count: number): string {
    return `${formatCount(count)} flaky ${count === 1 ? "tree" : "trees"}`;
  }
</script>

{#snippet trees(gate: FlakyGate)}
  <Badge tone="flaky" title={treeText(gate.tree_count)}>{formatCount(gate.tree_count)}</Badge>
{/snippet}

<Module
  title="Flaky gates"
  titleId="flaky-gates-title"
  loading={query.loading && !query.data}
  error={query.error}
  empty={!query.data || query.data.length === 0}
  emptyTitle={emptyTitle("flaky gates", { range: filters.range, repoLabel })}
  emptyDetail={emptyHint({ range: filters.range, repoLabel, recording: freshness.recording })}
>
  <DataTable
    label="Flaky gates"
    bare
    {rows}
    rowKey={gateKey}
    columns={[
      { key: "name", label: "Gate", sortable: false },
      { key: "repo_name", label: "Repo", sortable: false, title: (g) => g.repo ?? undefined },
      { key: "tree_count", label: "Flaky trees", align: "right", sortable: false, cell: trees },
    ]}
    onRowClick={(g) => openGatePanel(g)}
    rowLabel={(g) => `Open ${g.name}`}
    busy={query.loading}
  />
  <a class="more-link" href={href({ page: "flaky" })}>All flaky gates <span aria-hidden="true">→</span></a>
</Module>
