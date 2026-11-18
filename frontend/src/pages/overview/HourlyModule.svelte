<!--
  @component
  When gates run: activity by weekday and hour in the browser's time zone, which the header
  names, with tabs that pick runs, time saved, or failures. A cell opens Activity filtered to
  its weekday and hour.

  Props:
  - `repoLabel`: the repo selection's display name, or null for all repos
  - `span`: page-local days the overview is scoped to, if any
-->
<script lang="ts">
  import { getHourly, spanScope, type Outcome } from "../../lib/api";
  import HourHeatmap from "../../lib/components/HourHeatmap.svelte";
  import MetricTabs from "../../lib/components/MetricTabs.svelte";
  import Module from "../../lib/components/Module.svelte";
  import { HEAT_OPTIONS, type HeatMetric } from "../../lib/heat";
  import { createQuery } from "../../lib/query.svelte";
  import { activityHref } from "../../lib/router.svelte";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import type { DaySpan } from "../../lib/selection";
  import { filters, freshness, timeZone } from "../../lib/state.svelte";

  interface Props {
    repoLabel: string | null;
    /** Page-local days the overview is scoped to. */
    span?: DaySpan;
  }

  let { repoLabel, span }: Props = $props();

  const query = createQuery(
    (signal) => getHourly({ signal, scope: spanScope(span) }),
    () => span,
  );

  let metric: HeatMetric = $state("runs");

  // A cell links to the runs its value counts: every run, the skips that saved time, or the
  // failures.
  const METRIC_OUTCOME: Record<HeatMetric, { outcome?: Outcome }> = {
    runs: {},
    saved: { outcome: "skip" },
    fail: { outcome: "fail" },
  };
</script>

<Module
  title="When gates run"
  titleId="hourly-title"
  noun="hourly activity"
  loading={query.loading && !query.data}
  error={query.error}
  empty={query.data?.every((cell) => cell.runs === 0) ?? false}
  emptyTitle={emptyTitle("runs", { range: filters.range, span, repoLabel })}
  emptyDetail={emptyHint({ range: filters.range, span, repoLabel, recording: freshness.recording })}
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
    <HourHeatmap cells={query.data} {metric} href={(weekday, hour) => activityHref({ slot: { weekday, hour }, ...METRIC_OUTCOME[metric] }, span)} />
  {/if}
</Module>

<style>
  .zone {
    color: var(--text-faint);
    font-size: var(--text-xs);
  }
</style>
