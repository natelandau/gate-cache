<!--
  @component
  When gates run: activity by weekday and hour in the browser's time zone, which the header
  names, with tabs that pick runs, time saved, or failures.

  Props:
  - `repoLabel`: the repo selection's display name, or null for all repos
-->
<script lang="ts">
  import { getHourly } from "../../lib/api";
  import HourHeatmap from "../../lib/components/HourHeatmap.svelte";
  import MetricTabs from "../../lib/components/MetricTabs.svelte";
  import Module from "../../lib/components/Module.svelte";
  import { HEAT_OPTIONS, type HeatMetric } from "../../lib/heat";
  import { createQuery } from "../../lib/query.svelte";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import { filters, freshness, timeZone } from "../../lib/state.svelte";

  interface Props {
    repoLabel: string | null;
  }

  let { repoLabel }: Props = $props();

  const query = createQuery((signal) => getHourly({ signal }));

  let metric: HeatMetric = $state("runs");
</script>

<Module
  title="When gates run"
  titleId="hourly-title"
  noun="hourly activity"
  loading={query.loading && !query.data}
  error={query.error}
  empty={query.data?.every((cell) => cell.runs === 0) ?? false}
  emptyTitle={emptyTitle("runs", { range: filters.range, repoLabel })}
  emptyDetail={emptyHint({ range: filters.range, repoLabel, recording: freshness.recording })}
>
  {#snippet actions()}
    <span class="zone">{timeZone()}</span>
    <MetricTabs
      label="When gates run metric"
      options={HEAT_OPTIONS}
      value={metric}
      onchange={(v) => (metric = v as HeatMetric)}
    />
  {/snippet}
  {#if query.data}
    <HourHeatmap cells={query.data} {metric} />
  {/if}
</Module>

<style>
  .zone {
    color: var(--text-faint);
    font-size: var(--text-xs);
  }
</style>
