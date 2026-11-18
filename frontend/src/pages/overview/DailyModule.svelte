<!--
  @component
  The homepage daily chart: time saved over failures for each day of the range.

  Props:
  - `query`: the shell's summary query, whose days are already gap-filled
  - `repoLabel`: the repo selection's display name, or null for all repos
  - `span`: the picked days the overview is scoped to, if any
  - `onselect`: called with newly picked days, or undefined to clear them
-->
<script lang="ts">
  import DailyChart from "../../lib/components/DailyChart.svelte";
  import Module from "../../lib/components/Module.svelte";
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
    <DailyChart days={query.data.days} selected={span} {onselect} />
  {/if}
</Module>
