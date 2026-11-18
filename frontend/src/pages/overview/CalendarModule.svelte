<!--
  @component
  The homepage activity calendar: one cell per day of the range, with tabs that pick runs,
  time saved, or failures.

  Props:
  - `query`: the shell's summary query, whose days are already gap-filled
  - `repoLabel`: the repo selection's display name, or null for all repos
  - `span`: the picked days the overview is scoped to, if any
  - `onselect`: called with newly picked days, or undefined to clear them
-->
<script lang="ts">
  import { calendarFacts } from "../../lib/calendar";
  import CalendarHeatmap from "../../lib/components/CalendarHeatmap.svelte";
  import { formatCount, formatLongDay } from "../../lib/format";
  import MetricTabs from "../../lib/components/MetricTabs.svelte";
  import Module from "../../lib/components/Module.svelte";
  import { HEAT_OPTIONS, type HeatMetric } from "../../lib/heat";
  import type { Query } from "../../lib/query.svelte";
  import type { DaySpan } from "../../lib/selection";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import { filters, freshness } from "../../lib/state.svelte";
  import type { SummaryView } from "../../lib/summary";

  interface Props {
    query: Query<SummaryView>;
    repoLabel: string | null;
    span?: DaySpan;
    onselect: (span: DaySpan | undefined) => void;
  }

  let { query, repoLabel, span, onselect }: Props = $props();

  let metric: HeatMetric = $state("runs");

  const facts = $derived(query.data ? calendarFacts(query.data.days) : null);
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
    <CalendarHeatmap days={query.data.days} {metric} selected={span} {onselect} />
  {/if}
  {#if facts}
    <dl class="facts">
      <div>
        <dt>Busiest day</dt>
        <dd>{facts.busiest ? formatLongDay(facts.busiest.day) : "–"}</dd>
      </div>
      <div>
        <dt>Active days</dt>
        <dd>{formatCount(facts.activeDays)} / {formatCount(facts.totalDays)}</dd>
      </div>
      <div>
        <dt>Runs per active day</dt>
        <dd>{facts.runsPerActiveDay === null ? "–" : facts.runsPerActiveDay.toFixed(1)}</dd>
      </div>
    </dl>
  {/if}
</Module>

<style>
  .facts {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-2);
    margin: var(--space-4) 0 0;
    padding-top: 14px;
    border-top: 1px solid var(--border-row);
  }

  .facts div {
    display: flex;
    flex-direction: column-reverse;
    min-width: 0;
  }

  dt {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }

  dd {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    letter-spacing: -0.02em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
