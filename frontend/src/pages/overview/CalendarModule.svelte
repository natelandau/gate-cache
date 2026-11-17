<!--
  @component
  The homepage activity calendar: one cell per day of the range, with tabs that pick runs,
  time saved, or failures.

  Props:
  - `query`: the shell's summary query, whose days are already gap-filled
  - `repoLabel`: the repo selection's display name, or null for all repos
-->
<script lang="ts">
  import CalendarHeatmap from "../../lib/components/CalendarHeatmap.svelte";
  import MetricTabs from "../../lib/components/MetricTabs.svelte";
  import Module from "../../lib/components/Module.svelte";
  import { HEAT_OPTIONS, type HeatMetric } from "../../lib/heat";
  import type { Query } from "../../lib/query.svelte";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import { filters, freshness } from "../../lib/state.svelte";
  import type { SummaryView } from "../../lib/summary";

  interface Props {
    query: Query<SummaryView>;
    repoLabel: string | null;
  }

  let { query, repoLabel }: Props = $props();

  let metric: HeatMetric = $state("runs");
</script>

<Module
  title="Activity"
  titleId="calendar-title"
  loading={query.loading && !query.data}
  error={query.error}
  empty={query.data?.summary.runs === 0}
  emptyTitle={emptyTitle("runs", { range: filters.range, repoLabel })}
  emptyDetail={emptyHint({ range: filters.range, repoLabel, recording: freshness.recording })}
>
  {#snippet actions()}
    <MetricTabs
      label="Activity metric"
      options={HEAT_OPTIONS}
      value={metric}
      onchange={(v) => (metric = v as HeatMetric)}
    />
  {/snippet}
  {#if query.data}
    <CalendarHeatmap days={query.data.days} {metric} />
  {/if}
</Module>
