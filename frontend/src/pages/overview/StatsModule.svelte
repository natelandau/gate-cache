<!--
  @component
  The homepage stat strip: the headline numbers of the shared summary, each with its change
  against the previous window when the range has one. The run, flaky gate, and failure counts
  open Activity filtered to those runs.

  Props:
  - `query`: the summary query for the page's days
  - `span`: page-local days the overview is scoped to; the stat links carry them
  - `range`: the whole range's summary; its days feed the sparklines, which keep the whole
    range and highlight `span`
-->
<script lang="ts">
  import Notice from "../../lib/components/Notice.svelte";
  import StatStrip from "../../lib/components/StatStrip.svelte";
  import { deltaLabel } from "../../lib/deltas";
  import type { Query } from "../../lib/query.svelte";
  import { activityHref } from "../../lib/router.svelte";
  import type { DaySpan } from "../../lib/selection";
  import { pickedRange, summaryNote, summaryStats, type SummaryView } from "../../lib/summary";

  interface Props {
    /** Has no data until a summary for the picked days loads. */
    query: Query<SummaryView | undefined>;
    span?: DaySpan;
    range?: SummaryView;
  }

  let { query, span, range }: Props = $props();

  const summary = $derived(query.data?.summary);
  const stats = $derived(
    summary
      ? summaryStats(summary, {
          runsHref: activityHref({}, span),
          flakyHref: activityHref({ flaky: true }, span),
          failuresHref: activityHref({ outcome: "fail" }, span),
          costUnknownRuns: range?.summary.cost_unknown_runs,
        }, range?.days)
      : [],
  );
  const highlight = $derived(span && range ? pickedRange(range.days, query.data?.days) : undefined);
  const note = $derived(summary ? summaryNote(summary) : undefined);
  const label = $derived(summary?.previous ? deltaLabel(summary.previous) : undefined);
</script>

<div class="stats">
  {#if query.error}
    <Notice tone="error">Could not load the summary: {query.error.message}</Notice>
  {/if}
  {#if summary}
    <StatStrip {stats} {note} deltaLabel={label} busy={query.loading} {highlight} />
  {:else if query.loading}
    <p class="visually-hidden" aria-live="polite">Loading summary</p>
    <StatStrip stats={[]} placeholders={7} />
  {/if}
</div>

<style>
  .stats {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }

</style>
