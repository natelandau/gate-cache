<!--
  @component
  Time gates ran: one bar per day of the whole range, stacked by the gates that ran longest.
  Days are pickable like the Daily chart, and a gate in the legend opens its detail panel.

  Props:
  - `repoLabel`: the repo selection's display name, or null for all repos
  - `span`: the picked days the overview is scoped to, if any
  - `onselect`: called with newly picked days, or undefined to clear them
-->
<script lang="ts">
  import { TERMS } from "../../lib/terms";
  import type { SpentStatus } from "../../lib/api";
  import MetricTabs from "../../lib/components/MetricTabs.svelte";
  import Module from "../../lib/components/Module.svelte";
  import SpentChart from "../../lib/components/SpentChart.svelte";
  import { openGatePanel } from "../../lib/panel";
  import { createQuery } from "../../lib/query.svelte";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import type { DaySpan } from "../../lib/selection";
  import { loadSpent } from "../../lib/spent";
  import { filters, freshness } from "../../lib/state.svelte";

  interface Props {
    repoLabel: string | null;
    span?: DaySpan;
    onselect: (span: DaySpan | undefined) => void;
  }

  let { repoLabel, span, onselect }: Props = $props();

  let status: SpentStatus = $state("all");

  const options: { value: SpentStatus; label: string }[] = [
    { value: "all", label: "All" },
    { value: "passing", label: "Passing" },
    { value: "failing", label: "Failing" },
  ];

  const query = createQuery(
    (signal) => loadSpent(signal, status),
    () => status,
  );
</script>

<Module
  subtitle="Run time per day, by gate"
  title={TERMS.ran.label}
  titleId="spent-title"
  noun="run time"
  loading={query.loading && !query.data}
  error={query.error}
  empty={query.data?.series.length === 0}
  emptyTitle={emptyTitle(TERMS.ran.noun, { range: filters.range, repoLabel })}
  emptyDetail={emptyHint({ range: filters.range, repoLabel, recording: freshness.recording })}
>
  {#snippet actions()}
    <MetricTabs
      label="Runs included"
      {options}
      value={status}
      onchange={(v) => (status = v as SpentStatus)}
    />
  {/snippet}
  {#if query.data}
    <SpentChart
      rows={query.data.rows}
      series={query.data.series}
      selected={span}
      {onselect}
      onpickgate={(gate) => openGatePanel(gate)}
    />
  {/if}
</Module>
