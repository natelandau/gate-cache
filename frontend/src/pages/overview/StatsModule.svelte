<!--
  @component
  The homepage stat strip: the headline numbers of the shared summary, each with its change
  against the previous window when the range has one.

  Props:
  - `query`: the shell's summary query
-->
<script lang="ts">
  import Notice from "../../lib/components/Notice.svelte";
  import StatStrip from "../../lib/components/StatStrip.svelte";
  import { deltaLabel } from "../../lib/deltas";
  import type { Query } from "../../lib/query.svelte";
  import { href } from "../../lib/router.svelte";
  import { summaryNote, summaryStats, type SummaryView } from "../../lib/summary";

  interface Props {
    query: Query<SummaryView>;
  }

  let { query }: Props = $props();

  const summary = $derived(query.data?.summary);
  const stats = $derived(
    summary ? summaryStats(summary, { flakyHref: href({ page: "flaky" }) }) : [],
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
