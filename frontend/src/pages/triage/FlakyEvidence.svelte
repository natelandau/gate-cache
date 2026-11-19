<!--
  @component
  The evidence of a flaky gate: each tree that both failed and passed, newest first, with its
  runs oldest first, then the tests that flaked on those trees and the tests that passed on a
  retry.

  Props:
  - `item`: the flaky triage row
-->
<script lang="ts" module>
  export const FLAKY_TESTS_TITLE = "Flaky tests";
  export const RETRIED_TITLE = "Passed on retry";
</script>

<script lang="ts">
  import type { FlakyItem, FlakyTest, RetriedTest } from "../../lib/api";
  import DataTable, { type Column } from "../../lib/components/DataTable.svelte";
  import OutcomeBadge from "../../lib/components/OutcomeBadge.svelte";
  import { runSuffix, runTitle, shortTree } from "../../lib/events";
  import { formatCount, formatRelative, formatTimestamp, plural } from "../../lib/format";
  import { tally } from "../../lib/gates";
  import { clock } from "../../lib/state.svelte";

  interface Props {
    item: FlakyItem;
  }

  let { item }: Props = $props();

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

{#if item.evidence.trees.length}
  <ul class="evidence bare-list">
    {#each item.evidence.trees as tree (tree.tree)}
      {@const counts = tally(tree.runs)}
      <li class="entry">
        <div class="head">
          <span title={tree.tree}>{shortTree(tree.tree)}</span>
          <span class="muted small">
            {plural(counts.fails, "fail", "fails")}, {plural(counts.passes, "pass", "passes")}
          </span>
        </div>
        <ol class="runs bare-list" aria-label="Runs on tree {shortTree(tree.tree)}, oldest first">
          {#each tree.runs as run, index (index)}
            <li class="run">
              <OutcomeBadge outcome={run.outcome} title={runTitle(run)} />
              <span class="muted">{formatRelative(run.ts, clock.now)}</span>
              {#if runSuffix(run)}<span class="muted">{runSuffix(run)}</span>{/if}
            </li>
          {/each}
        </ol>
      </li>
    {/each}
  </ul>
{/if}
{#if item.evidence.tests.length}
  <section class="tests">
    <h3 class="section-title">{FLAKY_TESTS_TITLE}</h3>
    <DataTable
      bare
      label="Flaky tests of {item.name}"
      rows={item.evidence.tests}
      columns={testColumns}
      rowKey={(t) => t.name}
    />
  </section>
{/if}
{#if item.evidence.retried.length}
  <section class="tests">
    <h3 class="section-title">{RETRIED_TITLE}</h3>
    <DataTable
      bare
      label="Tests of {item.name} that passed on retry"
      rows={item.evidence.retried}
      columns={retriedColumns}
      rowKey={(t) => t.name}
    />
  </section>
{/if}

<style>
  .entry {
    display: grid;
    grid-template-columns: 200px minmax(0, 1fr);
    gap: var(--space-1) var(--space-3);
    align-items: center;
    padding: var(--space-2) var(--space-3);
    border-top: 1px solid var(--border);
  }

  .head {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
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

  .tests {
    padding: var(--space-2) var(--space-3);
    border-top: 1px solid var(--border);
  }

  .test-name {
    overflow-wrap: anywhere;
  }

  .muted {
    color: var(--text-muted);
  }

  .small {
    font-size: var(--text-xs);
  }

  @media (max-width: 720px) {
    .entry {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
