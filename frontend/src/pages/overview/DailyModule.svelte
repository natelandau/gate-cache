<!--
  @component
  The homepage daily chart: time saved over failures for each day of the range.

  Props:
  - `query`: the shell's summary query, whose days are already gap-filled
  - `repoLabel`: the repo selection's display name, or null for all repos
-->
<script lang="ts">
  import DailyChart from "../../lib/components/DailyChart.svelte";
  import Module from "../../lib/components/Module.svelte";
  import type { Query } from "../../lib/query.svelte";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import { filters, freshness } from "../../lib/state.svelte";
  import type { SummaryView } from "../../lib/summary";

  interface Props {
    query: Query<SummaryView>;
    repoLabel: string | null;
  }

  let { query, repoLabel }: Props = $props();
</script>

<Module
  title="Daily"
  titleId="daily-title"
  noun="daily totals"
  loading={query.loading && !query.data}
  error={query.error}
  empty={query.data?.summary.runs === 0}
  emptyTitle={emptyTitle("runs", { range: filters.range, repoLabel })}
  emptyDetail={emptyHint({ range: filters.range, repoLabel, recording: freshness.recording })}
>
  {#if query.data}
    <DailyChart days={query.data.days} />
  {/if}
</Module>
