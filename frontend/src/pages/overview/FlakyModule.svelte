<!--
  @component
  Flaky gates: the gates with the most flaky trees, each with a badge of its tree count. A
  row opens the gate's detail panel, and the badge opens the runs on those trees in Activity.

  Props:
  - `repoLabel`: the repo selection's display name, or null for all repos
  - `span`: page-local days the overview is scoped to, if any
-->
<script lang="ts">
  import Icon from "../../lib/components/Icon.svelte";
  import { getFlaky, spanScope, type FlakyGate } from "../../lib/api";
  import Badge from "../../lib/components/Badge.svelte";
  import DataTable from "../../lib/components/DataTable.svelte";
  import Module from "../../lib/components/Module.svelte";
  import { formatCount } from "../../lib/format";
  import { gateKey } from "../../lib/gates";
  import { openGatePanel } from "../../lib/panel";
  import { createQuery } from "../../lib/query.svelte";
  import { topFlaky } from "../../lib/rank";
  import { activityHref, href } from "../../lib/router.svelte";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import type { DaySpan } from "../../lib/selection";
  import { filters, freshness } from "../../lib/state.svelte";

  interface Props {
    repoLabel: string | null;
    /** Page-local days the overview is scoped to. */
    span?: DaySpan;
  }

  let { repoLabel, span }: Props = $props();

  const query = createQuery(
    (signal) => getFlaky({ signal, scope: spanScope(span) }),
    () => span,
  );

  const rows = $derived(topFlaky(query.data ?? []));

  function treeText(count: number): string {
    return `${formatCount(count)} flaky ${count === 1 ? "tree" : "trees"}`;
  }
</script>

{#snippet trees(gate: FlakyGate)}
  <a
    class="trees"
    href={activityHref({ gate: { repo: gate.repo, name: gate.name }, flaky: true }, span)}
    aria-label="{treeText(gate.tree_count)} for {gate.name}. Open their runs in Activity"
  >
    <Badge tone="flaky" title={treeText(gate.tree_count)}>{formatCount(gate.tree_count)}</Badge>
  </a>
{/snippet}

<Module
  title="Flaky gates"
  titleId="flaky-gates-title"
  loading={query.loading && !query.data}
  error={query.error}
  empty={!query.data || query.data.length === 0}
  emptyTitle={emptyTitle("flaky gates", { range: filters.range, span, repoLabel })}
  emptyDetail={emptyHint({ range: filters.range, span, repoLabel, recording: freshness.recording })}
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
  {#snippet footer()}
    <a class="more-link" href={href({ page: "flaky" })}>All flaky gates <Icon name="arrow-right" size={14} /></a>
  {/snippet}
</Module>

<style>
  .trees {
    text-decoration: none;
  }

  .trees:hover :global(.badge) {
    text-decoration: underline;
  }
</style>
