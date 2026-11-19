<script lang="ts" module>
  export const RETRIED_TITLE = "Passed on retry";
  export const FLAKY_LEDE =
    "Gates where the same tree both failed and passed, and tests that passed on a retry. Runs are oldest first.";
</script>

<script lang="ts">
  import GateName from "../lib/components/GateName.svelte";
  import { getFlaky, type FlakyTest, type RetriedTest } from "../lib/api";
  import DataTable, { type Column } from "../lib/components/DataTable.svelte";
  import EmptyState from "../lib/components/EmptyState.svelte";
  import Notice from "../lib/components/Notice.svelte";
  import OutcomeBadge from "../lib/components/OutcomeBadge.svelte";
  import PageHeader from "../lib/components/PageHeader.svelte";
  import { eventTitle, shortTree, timeText } from "../lib/events";
  import { formatCount, formatRelative, formatTimestamp, plural } from "../lib/format";
  import { gateKey, tally } from "../lib/gates";
  import { createQuery } from "../lib/query.svelte";
  import { href } from "../lib/router.svelte";
  import { emptyHint, emptyTitle, scopeSubtitle } from "../lib/scope";
  import { clock, filters, freshness } from "../lib/state.svelte";
  import { TESTS_CUTOFF_NOTE } from "./GateDetail.svelte";

  interface Props {
    repoLabel: string | null;
  }

  let { repoLabel }: Props = $props();

  const query = createQuery((signal) => getFlaky({ signal }));
  const subtitle = $derived(scopeSubtitle(repoLabel, filters.range));
  const gates = $derived(query.data?.gates ?? []);
  const showCutoff = $derived(
    query.data?.tests_cutoff != null && gates.some((g) => g.tests.length || g.retried.length),
  );

  const testName = <T extends { name: string }>(): Column<T> => ({
    key: "name",
    label: "Test",
    cell: testNameCell,
    title: (t) => t.name,
  });

  const lastSeen = <T extends { last: number }>(): Column<T> => ({
    key: "last",
    label: "Last seen",
    align: "right",
    text: (t) => formatRelative(t.last, clock.now),
    title: (t) => formatTimestamp(t.last),
  });

  const testColumns: Column<FlakyTest>[] = [
    testName<FlakyTest>(),
    { key: "fails", label: "Fails", align: "right", text: (t) => formatCount(t.fails) },
    { key: "passes", label: "Passes", align: "right", text: (t) => formatCount(t.passes) },
    lastSeen<FlakyTest>(),
  ];

  const retriedColumns: Column<RetriedTest>[] = [
    testName<RetriedTest>(),
    { key: "runs", label: "Runs", align: "right", text: (t) => formatCount(t.runs) },
    lastSeen<RetriedTest>(),
  ];
</script>

{#snippet testNameCell(t: { name: string })}<span class="test-name">{t.name}</span>{/snippet}

<section class="page" aria-labelledby="flaky-title">
  <div>
    <PageHeader title="Flaky" headingId="flaky-title" {subtitle} />
    <p class="lede">{FLAKY_LEDE}</p>
  </div>

  {#if query.error}
    <Notice tone="error">Could not load flaky gates: {query.error.message}</Notice>
  {/if}

  {#if query.data}
    {#if gates.length === 0}
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
        {#each gates as gate (gateKey(gate))}
          <li class="panel">
            <header class="gate-head">
              <h2 class="gate-name">
                <a href={href({ page: "gate", repo: gate.repo, name: gate.name })}><GateName name={gate.name} /></a>
              </h2>
              <span class="muted" title={gate.repo ?? undefined}>{gate.repo_name}</span>
              <span class="meta">
                {#if gate.tree_count}{plural(gate.tree_count, "tree", "trees")} · {/if}last seen
                <span title={formatTimestamp(gate.last_seen)}>
                  {formatRelative(gate.last_seen, clock.now)}
                </span>
              </span>
            </header>
            <div class="gate-body">
              {#if gate.trees.length}
                <ul class="trees">
                  {#each gate.trees as tree (tree.tree)}
                    {@const counts = tally(tree.runs)}
                    <li class="tree">
                      <div class="tree-head">
                        <span title={tree.tree}>{shortTree(tree.tree)}</span>
                        <span class="muted">
                          {plural(counts.fails, "fail", "fails")}, {plural(counts.passes, "pass", "passes")}
                        </span>
                      </div>
                      <ol class="runs" aria-label="Runs on tree {shortTree(tree.tree)}, oldest first">
                        {#each tree.runs as run, index (index)}
                          <li class="run">
                            <OutcomeBadge outcome={run.outcome} title={`${eventTitle(run)} · ${timeText(run)}`} />
                            <span class="muted">{formatRelative(run.ts, clock.now)}</span>
                            {#if run.name !== run.gate}<span class="muted">{run.name.slice(run.gate.length)}</span>{/if}
                          </li>
                        {/each}
                      </ol>
                    </li>
                  {/each}
                </ul>
              {/if}
              {#if gate.tests.length}
                <section class="tests">
                  <h3 class="section-title">Flaky tests</h3>
                  <DataTable
                    bare
                    label="Flaky tests of {gate.name}"
                    rows={gate.tests}
                    columns={testColumns}
                    rowKey={(t) => t.name}
                  />
                </section>
              {/if}
              {#if gate.retried.length}
                <section class="tests">
                  <h3 class="section-title">{RETRIED_TITLE}</h3>
                  <DataTable
                    bare
                    label="Tests of {gate.name} that passed on retry"
                    rows={gate.retried}
                    columns={retriedColumns}
                    rowKey={(t) => t.name}
                  />
                </section>
              {/if}
            </div>
          </li>
        {/each}
      </ul>
      {#if showCutoff}
        <p class="muted note">{TESTS_CUTOFF_NOTE}</p>
      {/if}
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

  .note {
    margin: 0;
    font-size: var(--text-xs);
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

  /* A divider between whichever of the tree list and the test groups a gate has. */
  .gate-body > * + * {
    border-top: 1px solid var(--border);
  }

  .tests {
    padding: var(--space-2) var(--space-3);
  }

  .test-name {
    overflow-wrap: anywhere;
  }

  @media (max-width: 720px) {
    .tree {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
