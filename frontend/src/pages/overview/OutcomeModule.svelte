<!--
  @component
  Outcome mix: the share of each outcome over the range as one stacked bar with a legend.

  Props:
  - `query`: the shell's summary query
  - `repoLabel`: the repo selection's display name, or null for all repos
-->
<script lang="ts">
  import Module from "../../lib/components/Module.svelte";
  import OutcomeMix from "../../lib/components/OutcomeMix.svelte";
  import type { Query } from "../../lib/query.svelte";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import { filters, freshness } from "../../lib/state.svelte";
  import type { SummaryView } from "../../lib/summary";

  interface Props {
    query: Query<SummaryView>;
    repoLabel: string | null;
  }

  let { query, repoLabel }: Props = $props();

  const outcomes = $derived(query.data?.summary.outcomes);
  const total = $derived(outcomes ? Object.values(outcomes).reduce((sum, n) => sum + n, 0) : 0);
</script>

<Module
  title="Outcome mix"
  titleId="outcome-title"
  noun="outcomes"
  loading={query.loading && !query.data}
  error={query.error}
  empty={!outcomes || total === 0}
  emptyTitle={emptyTitle("runs", { range: filters.range, repoLabel })}
  emptyDetail={emptyHint({ range: filters.range, repoLabel, recording: freshness.recording })}
>
  {#if outcomes}
    <OutcomeMix counts={outcomes} />
  {/if}
</Module>
