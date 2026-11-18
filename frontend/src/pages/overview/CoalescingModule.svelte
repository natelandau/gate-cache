<!--
  @component
  Waits for concurrent runs: how many runs waited for another run of the same gate, how each
  wait ended as a `ShareMix`, and the total and typical wait.

  Props:
  - `repoLabel`: the repo selection's display name, or null for all repos
  - `span`: page-local days the overview is scoped to, if any
-->
<script lang="ts">
  import { getCoalescing, spanScope } from "../../lib/api";
  import { COALESCING_HINT, coalescingNote, waitEndings, waitFacts } from "../../lib/coalescing";
  import Module from "../../lib/components/Module.svelte";
  import ShareMix from "../../lib/components/ShareMix.svelte";
  import { createQuery } from "../../lib/query.svelte";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import type { DaySpan } from "../../lib/selection";
  import { filters, freshness } from "../../lib/state.svelte";

  interface Props {
    repoLabel: string | null;
    span?: DaySpan;
  }

  let { repoLabel, span }: Props = $props();

  const query = createQuery(
    (signal) => getCoalescing({ signal, scope: spanScope(span) }),
    () => span,
  );

  const data = $derived(query.data);
  const endings = $derived(data ? waitEndings(data) : []);
  const facts = $derived(data ? waitFacts(data) : []);
  const note = $derived(data ? coalescingNote(data) : undefined);
  const empty = $derived(!data || data.waited === 0);
  const emptyDetail = $derived(
    data?.runs
      ? (note ?? COALESCING_HINT)
      : emptyHint({ range: filters.range, span, repoLabel, recording: freshness.recording }),
  );
</script>

<Module
  title="Waits for concurrent runs"
  titleId="coalescing-title"
  noun="waits"
  loading={query.loading && !query.data}
  error={query.error}
  {empty}
  emptyTitle={emptyTitle("calls that waited for another run", { range: filters.range, span, repoLabel })}
  {emptyDetail}
>
  <dl class="facts">
    {#each facts as fact (fact.label)}
      <div class="fact">
        <dt>{fact.label}</dt>
        <dd class="value">{fact.value}</dd>
      </div>
    {/each}
  </dl>
  <ShareMix parts={endings} />
  {#if note}<p class="note">{note}</p>{/if}
</Module>

<style>
  .facts {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-2) var(--space-3);
    margin: 0 0 var(--space-3);
    padding: 0;
  }

  .fact {
    min-width: 0;
  }

  dt {
    font-size: var(--text-xs);
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  dd {
    margin: 2px 0 0;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .note {
    margin: var(--space-2) 0 0;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }
</style>
