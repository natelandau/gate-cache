<!--
  @component
  The evidence of a gate with failed spot checks: the newest of them, each with its time, tree,
  outcome, and exit code, and a link to that day's failed spot checks of the gate in Activity.

  Props:
  - `item`: the failed spot check triage row
-->
<script lang="ts">
  import type { FailedSpotCheckItem, EventRow } from "../../lib/api";
  import OutcomeBadge from "../../lib/components/OutcomeBadge.svelte";
  import { runSuffix, runTitle, shortTree } from "../../lib/events";
  import { dayKey } from "../../lib/fill";
  import { formatCount, formatRelative, formatTimestamp } from "../../lib/format";
  import { activityHref } from "../../lib/router.svelte";
  import { clock, timeZone } from "../../lib/state.svelte";
  import { TRIAGE } from "../../lib/terms";

  interface Props {
    item: FailedSpotCheckItem;
  }

  let { item }: Props = $props();

  const filter = $derived({
    gate: { repo: item.repo, name: item.name },
    spotCheck: true as const,
    outcome: "fail" as const,
  });

  function runHref(run: EventRow): string {
    const day = dayKey(run.ts, timeZone());
    return activityHref(filter, { from: day, to: day });
  }
</script>

<ol class="evidence bare-list" aria-label="Failed spot checks of {item.name}, newest first">
  {#each item.evidence.runs as run, index (index)}
    <li class="entry">
      <a href={runHref(run)} title={formatTimestamp(run.ts)}>{formatRelative(run.ts, clock.now)}</a>
      <span title={run.tree ?? undefined}>{shortTree(run.tree)}</span>
      <span class="result">
        <OutcomeBadge outcome={run.outcome} title={runTitle(run)} />
        <span class="muted">
          {#if run.exit_code !== null}{TRIAGE.exitCode} {run.exit_code}{/if}
          {runSuffix(run)}
        </span>
      </span>
    </li>
  {/each}
</ol>
<p class="foot">
  {#if item.evidence.count > item.evidence.runs.length}
    <span class="muted">
      {TRIAGE.shownOf(formatCount(item.evidence.runs.length), formatCount(item.evidence.count))}
    </span>
  {/if}
  <a href={activityHref(filter)}>{TRIAGE.allSpotChecks}</a>
</p>

<style>
  .entry {
    display: grid;
    grid-template-columns: 200px 200px minmax(0, 1fr);
    gap: var(--space-1) var(--space-3);
    align-items: baseline;
    padding: var(--space-2) var(--space-3);
    border-top: 1px solid var(--border);
    font-size: var(--text-sm);
  }

  .result {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
  }

  .foot {
    display: flex;
    gap: var(--space-3);
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-top: 1px solid var(--border);
    font-size: var(--text-sm);
  }

  a {
    color: var(--accent);
  }

  .muted {
    color: var(--text-muted);
  }

  @media (max-width: 720px) {
    .entry {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
