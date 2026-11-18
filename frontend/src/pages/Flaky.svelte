<script lang="ts">
  import { getFlaky } from "../lib/api";
  import EmptyState from "../lib/components/EmptyState.svelte";
  import Notice from "../lib/components/Notice.svelte";
  import OutcomeBadge from "../lib/components/OutcomeBadge.svelte";
  import PageHeader from "../lib/components/PageHeader.svelte";
  import { eventTitle, shortTree, timeText } from "../lib/events";
  import { formatRelative, formatTimestamp, plural } from "../lib/format";
  import { gateKey, tally } from "../lib/gates";
  import { createQuery } from "../lib/query.svelte";
  import { href } from "../lib/router.svelte";
  import { emptyHint, emptyTitle, scopeSubtitle } from "../lib/scope";
  import { clock, filters, freshness } from "../lib/state.svelte";

  interface Props {
    repoLabel: string | null;
  }

  let { repoLabel }: Props = $props();

  const query = createQuery((signal) => getFlaky({ signal }));
  const subtitle = $derived(scopeSubtitle(repoLabel, filters.range));

</script>

<section class="page" aria-labelledby="flaky-title">
  <div>
    <PageHeader title="Flaky" headingId="flaky-title" {subtitle} />
    <p class="lede">Gates where the same tree both failed and passed. Runs are oldest first.</p>
  </div>

  {#if query.error}
    <Notice tone="error">Could not load flaky gates: {query.error.message}</Notice>
  {/if}

  {#if query.data}
    {#if query.data.length === 0}
      <div class="panel">
        <EmptyState
          title={emptyTitle("flaky gates", { range: filters.range, repoLabel })}
          detail={emptyHint({ range: filters.range, repoLabel, recording: freshness.recording })}
        >
          <p class="definition">A gate is flaky when it both fails and passes on the same tree.</p>
        </EmptyState>
      </div>
    {:else}
      <ul class="gates" aria-busy={query.loading} class:busy={query.loading}>
        {#each query.data as gate (gateKey(gate))}
          <li class="panel">
            <header class="gate-head">
              <h2 class="gate-name">
                <a href={href({ page: "gate", repo: gate.repo, name: gate.name })}>{gate.name}</a>
              </h2>
              <span class="muted" title={gate.repo ?? undefined}>{gate.repo_name}</span>
              <span class="meta">
                {plural(gate.tree_count, "tree", "trees")} · last seen
                <span title={formatTimestamp(gate.last_seen)}>
                  {formatRelative(gate.last_seen, clock.now)}
                </span>
              </span>
            </header>
            <ul class="trees">
              {#each gate.trees as tree (tree.tree)}
                {@const counts = tally(tree.runs)}
                <li class="tree">
                  <div class="tree-head">
                    <span class="tree-hash" title={tree.tree}>{shortTree(tree.tree)}</span>
                    <span class="muted">
                      {plural(counts.fails, "fail", "fails")}, {plural(counts.passes, "pass", "passes")}
                    </span>
                  </div>
                  <ol class="runs" aria-label="Runs on tree {shortTree(tree.tree)}, oldest first">
                    {#each tree.runs as run, index (index)}
                      <li class="run">
                        <OutcomeBadge outcome={run.outcome} title={`${eventTitle(run)} · ${timeText(run)}`} />
                        <span class="muted">{formatRelative(run.ts, clock.now)}</span>
                      </li>
                    {/each}
                  </ol>
                </li>
              {/each}
            </ul>
          </li>
        {/each}
      </ul>
    {/if}
  {:else if query.loading}
    <p class="muted" aria-live="polite">Loading flaky gates</p>
  {/if}
</section>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .lede {
    margin: var(--space-2) 0 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  .definition {
    margin: 0;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  .panel {
    border: 1px solid var(--border);
    border-radius: var(--radius-control);
    background: var(--surface);
  }

  ul,
  ol {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .gates {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .busy {
    opacity: 0.55;
  }

  .gate-head {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-3);
    padding: var(--space-2) var(--space-3);
    background: var(--surface-sunken);
    border-bottom: 1px solid var(--border);
    border-radius: var(--radius-control) var(--radius-control) 0 0;
  }

  .gate-name {
    font-size: var(--text-md);
  }

  .gate-name a {
    color: var(--text);
    text-decoration-color: var(--border-strong);
    text-underline-offset: 3px;
  }

  .gate-name a:hover {
    text-decoration-color: currentColor;
  }

  .meta {
    margin-left: auto;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  .tree {
    display: grid;
    grid-template-columns: 200px minmax(0, 1fr);
    gap: var(--space-1) var(--space-3);
    align-items: center;
    padding: var(--space-2) var(--space-3);
    border-top: 1px solid var(--border);
  }

  .tree:first-child {
    border-top: 0;
  }

  .tree-head {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
  }

  .tree-head .muted {
    font-size: var(--text-xs);
  }

  .runs {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-3);
  }

  .run {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: var(--text-sm);
  }

  .muted {
    color: var(--text-muted);
  }

  @media (max-width: 720px) {
    .tree {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
