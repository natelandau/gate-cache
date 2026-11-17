<script lang="ts">
  import DailyChart from "../lib/components/DailyChart.svelte";
  import EmptyState from "../lib/components/EmptyState.svelte";
  import Notice from "../lib/components/Notice.svelte";
  import StatStrip from "../lib/components/StatStrip.svelte";
  import type { Query } from "../lib/query.svelte";
  import { href } from "../lib/router.svelte";
  import { emptyHint, emptyTitle } from "../lib/scope";
  import { filters, freshness } from "../lib/state.svelte";
  import { summaryNote, summaryStats, type SummaryView } from "../lib/summary";

  interface Props {
    /** The shell's summary query, shared with the sidebar's flaky badge. */
    query: Query<SummaryView>;
    repoLabel: string | null;
  }

  let { query, repoLabel }: Props = $props();

  const stats = $derived(
    query.data ? summaryStats(query.data.summary, { flakyHref: href({ page: "flaky" }) }) : [],
  );
  const note = $derived(query.data ? summaryNote(query.data.summary) : undefined);
</script>

<section class="page" aria-labelledby="overview-title">
  <h1 id="overview-title" class="page-title">Overview</h1>

  {#if query.error}
    <Notice tone="error">Could not load the summary: {query.error.message}</Notice>
  {/if}

  {#if query.data}
    {#if query.data.summary.runs === 0}
      <div class="panel">
        <EmptyState
          title={emptyTitle("runs", { range: filters.range, repoLabel })}
          detail={emptyHint({ range: filters.range, repoLabel, recording: freshness.recording })}
        />
      </div>
    {:else}
      <StatStrip {stats} {note} busy={query.loading} />
      <div>
        <h2 class="section-title">Daily</h2>
        <DailyChart days={query.data.days} />
      </div>
    {/if}
  {:else if query.loading}
    <p class="loading" aria-live="polite">Loading summary</p>
  {/if}
</section>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .panel {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
  }

  .loading {
    margin: 0;
    color: var(--text-muted);
  }
</style>
