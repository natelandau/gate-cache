<!--
  @component
  Outcome mix: the share of each outcome over the range as one stacked bar with a legend. Each
  count opens Activity filtered to that outcome.

  Props:
  - `query`: the shell's summary query
  - `repoLabel`: the repo selection's display name, or null for all repos
  - `span`: page-local days the overview is scoped to, if any
-->
<script lang="ts">
  import Module from "../../lib/components/Module.svelte";
  import OutcomeMix from "../../lib/components/OutcomeMix.svelte";
  import type { Query } from "../../lib/query.svelte";
  import { activityHref } from "../../lib/router.svelte";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import type { DaySpan } from "../../lib/selection";
  import { filters, freshness } from "../../lib/state.svelte";
  import type { SummaryView } from "../../lib/summary";

  interface Props {
    /** Has no data until a summary for the picked days loads. */
    query: Query<SummaryView | undefined>;
    repoLabel: string | null;
    /** Page-local days the overview is scoped to. */
    span?: DaySpan;
  }

  let { query, repoLabel, span }: Props = $props();

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
  emptyTitle={emptyTitle("gate calls", { range: filters.range, span, repoLabel })}
  emptyDetail={emptyHint({ range: filters.range, span, repoLabel, recording: freshness.recording })}
>
  {#if outcomes}
    <OutcomeMix counts={outcomes} href={(outcome) => activityHref({ outcome }, span)} />
  {/if}
</Module>
