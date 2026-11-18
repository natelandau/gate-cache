<!--
  @component
  The homepage stat strip: the headline numbers of the shared summary, each with its change
  against the previous window when the range has one. The run, flaky gate, and failure counts
  open Activity filtered to those runs.

  Props:
  - `query`: the summary query for the page's days
  - `span`: page-local days the overview is scoped to; the stat links carry them
-->
<script lang="ts">
  import Notice from "../../lib/components/Notice.svelte";
  import StatStrip from "../../lib/components/StatStrip.svelte";
  import { deltaLabel } from "../../lib/deltas";
  import type { Query } from "../../lib/query.svelte";
  import { activityHref } from "../../lib/router.svelte";
  import type { DaySpan } from "../../lib/selection";
  import { summaryNote, summaryStats, type SummaryView } from "../../lib/summary";

  interface Props {
    /** Has no data until a summary for the picked days loads. */
    query: Query<SummaryView | undefined>;
    span?: DaySpan;
  }

  let { query, span }: Props = $props();

  const summary = $derived(query.data?.summary);
  const stats = $derived(
    summary
      ? summaryStats(summary, {
          runsHref: activityHref({}, span),
          flakyHref: activityHref({ flaky: true }, span),
          failuresHref: activityHref({ outcome: "fail" }, span),
        })
      : [],
  );
  const note = $derived(summary ? summaryNote(summary) : undefined);
  const label = $derived(summary?.previous ? deltaLabel(summary.previous) : undefined);
</script>

<div class="stats">
  {#if query.error}
    <Notice tone="error">Could not load the summary: {query.error.message}</Notice>
  {/if}
  {#if summary}
    <StatStrip {stats} {note} deltaLabel={label} busy={query.loading} />
  {:else if query.loading}
    <p class="loading" aria-live="polite">Loading summary</p>
  {/if}
</div>

<style>
  .stats {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }

  .loading {
    margin: 0;
    color: var(--text-muted);
  }
</style>
