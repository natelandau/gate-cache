<!--
  @component
  The homepage stat strip: the headline numbers of the shared summary, each with its change
  against the previous window when the range has one. The run, flaky gate, and failure counts
  open Activity filtered to those runs.

  Props:
  - `query`: the summary query for the page's days
  - `span`: page-local days the overview is scoped to; the stat links carry them
  - `days`: the whole range's daily buckets for the sparklines, which keep the whole range
    and highlight `span`
-->
<script lang="ts">
  import Notice from "../../lib/components/Notice.svelte";
  import Skeleton from "../../lib/components/Skeleton.svelte";
  import StatStrip from "../../lib/components/StatStrip.svelte";
  import { deltaLabel } from "../../lib/deltas";
  import type { DayBucket } from "../../lib/fill";
  import type { Query } from "../../lib/query.svelte";
  import { activityHref } from "../../lib/router.svelte";
  import type { DaySpan } from "../../lib/selection";
  import { summaryNote, summaryStats, type SummaryView } from "../../lib/summary";

  interface Props {
    /** Has no data until a summary for the picked days loads. */
    query: Query<SummaryView | undefined>;
    span?: DaySpan;
    days?: DayBucket[];
  }

  let { query, span, days }: Props = $props();

  const summary = $derived(query.data?.summary);
  const stats = $derived(
    summary
      ? summaryStats(summary, {
          runsHref: activityHref({}, span),
          flakyHref: activityHref({ flaky: true }, span),
          failuresHref: activityHref({ outcome: "fail" }, span),
        }, days)
      : [],
  );
  const highlight = $derived.by((): [number, number] | undefined => {
    if (!span || !days) return undefined;
    const from = days.findIndex((d) => d.day >= span.from);
    const after = days.findIndex((d) => d.day > span.to);
    const to = (after < 0 ? days.length : after) - 1;
    return from >= 0 && to >= from ? [from, to] : undefined;
  });
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
    <div class="skeletons">
      {#each { length: 7 }, i (i)}<div class="card"><Skeleton height={12} width="60%" /><Skeleton height={28} width="75%" /><Skeleton height={12} width="85%" /></div>{/each}
    </div>
  {/if}
</div>

<style>
  .stats {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }

  .skeletons {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: var(--space-3);
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px var(--space-4);
    border-radius: var(--radius-card);
    background: var(--surface);
    box-shadow: var(--ring);
  }
</style>
