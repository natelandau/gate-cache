<!--
  @component
  One repo's numbers over the global range: headline stats, the daily chart, its gates, and
  its latest failures. It shows its own repo whatever the global repo filter selects. Gate and
  failure rows open the gate panel over this page; closing it focuses the gate's row.

  Props:
  - `repo`: the repo's git common directory
  - `label`: the repo's display name
  - `open`: the gate whose panel is open, if any
-->
<script lang="ts">
  import { getActivity, getGates, type EventRow } from "../lib/api";
  import Button from "../lib/components/Button.svelte";
  import DailyChart from "../lib/components/DailyChart.svelte";
  import DataTable, { type Column } from "../lib/components/DataTable.svelte";
  import EmptyState from "../lib/components/EmptyState.svelte";
  import GateTable from "../lib/components/GateTable.svelte";
  import Notice from "../lib/components/Notice.svelte";
  import StatStrip from "../lib/components/StatStrip.svelte";
  import { eventKeys } from "../lib/events";
  import { formatDuration, formatRelative, formatTimestamp } from "../lib/format";
  import { gateKey } from "../lib/gates";
  import { closeGatePanel, openGatePanel } from "../lib/panel";
  import { createQuery } from "../lib/query.svelte";
  import { href, navigate } from "../lib/router.svelte";
  import { emptyHint, emptyTitle } from "../lib/scope";
  import { clock, filters, freshness, setRepo } from "../lib/state.svelte";
  import { loadSummary, summaryNote, summaryStats } from "../lib/summary";
  import GateDetail from "./GateDetail.svelte";

  interface Props {
    repo: string;
    label: string;
    open: { repo: string | null; name: string } | null;
  }

  let { repo, label, open }: Props = $props();

  const FAILURE_LIMIT = 20;

  const summary = createQuery(
    (signal) => loadSummary(signal, repo),
    () => repo,
  );
  const gates = createQuery(
    (signal) => getGates({ signal, repo }),
    () => repo,
  );
  const failures = createQuery(
    (signal) => getActivity({ limit: FAILURE_LIMIT, outcome: "fail" }, { signal, repo }),
    () => repo,
  );

  // The Flaky page follows the global repo filter, so a link there could show other repos.
  const stats = $derived(summary.data ? summaryStats(summary.data.summary) : []);
  const note = $derived(summary.data ? summaryNote(summary.data.summary) : undefined);
  const noRuns = $derived(summary.data?.summary.runs === 0);
  const scopeText = $derived({ range: filters.range, repoLabel: label });
  // The global repo filter does not apply here, so the hint must not suggest loosening it.
  const hint = $derived(
    emptyHint({ range: filters.range, repoLabel: null, recording: freshness.recording }),
  );

  const openKey = $derived(open ? gateKey(open) : null);

  type Failure = EventRow & { key: string };
  const failureRows = $derived.by<Failure[]>(() => {
    const events = failures.data?.events ?? [];
    const keys = eventKeys(events);
    return events.map((event, index) => ({ ...event, key: keys[index]! }));
  });

  const failureColumns: Column<Failure>[] = [
    {
      key: "ts",
      label: "When",
      text: (e) => formatRelative(e.ts, clock.now),
      title: (e) => formatTimestamp(e.ts),
    },
    { key: "name", label: "Gate", cell: gateName },
    {
      key: "exit_code",
      label: "Exit code",
      align: "right",
      text: (e) => (e.exit_code === null ? "n/a" : String(e.exit_code)),
    },
    { key: "duration", label: "Ran", align: "right", text: (e) => formatDuration(e.duration) },
  ];

  function filterToRepo(): void {
    setRepo(repo);
    navigate({ page: "overview" });
  }
</script>

{#snippet gateName(e: Failure)}<span class="gate">{e.name}</span>{/snippet}

<section class="page" aria-labelledby="repo-title">
  <header class="head">
    <a class="back" href={href({ page: "repos" })}>Back to repos</a>
    <div class="title-row">
      <div class="titles">
        <h1 id="repo-title" class="page-title">{label}</h1>
        <p class="path mono">{repo}</p>
      </div>
      <Button onclick={filterToRepo}>Filter dashboard to this repo</Button>
    </div>
  </header>

  {#if summary.error}
    <Notice tone="error">Could not load the summary: {summary.error.message}</Notice>
  {/if}

  {#if summary.data}
    {#if noRuns}
      <div class="panel">
        <EmptyState title={emptyTitle("runs", scopeText)} detail={hint} />
      </div>
    {:else}
      <StatStrip {stats} {note} busy={summary.loading} />
      <div>
        <h2 class="section-title">Daily</h2>
        <DailyChart days={summary.data.days} />
      </div>
    {/if}
  {:else if summary.loading}
    <p class="loading" aria-live="polite">Loading summary</p>
  {/if}

  {#if !noRuns}
    <section aria-labelledby="repo-gates-title">
      <h2 id="repo-gates-title" class="section-title">Gates</h2>
      {#if gates.error}
        <Notice tone="error">Could not load gates: {gates.error.message}</Notice>
      {/if}
      {#if gates.data}
        <GateTable
          label="Gates in {label}"
          rows={gates.data}
          showRepo={false}
          activeKey={openKey}
          onRowClick={(g) => openGatePanel(g, open !== null)}
          busy={gates.loading}
        >
          {#snippet empty()}
            <EmptyState title={emptyTitle("runs", scopeText)} detail={hint} />
          {/snippet}
        </GateTable>
      {:else if gates.loading}
        <p class="loading" aria-live="polite">Loading gates</p>
      {/if}
    </section>

    <section aria-labelledby="repo-failures-title">
      <h2 id="repo-failures-title" class="section-title">Recent failures</h2>
      {#if failures.error}
        <Notice tone="error">Could not load failures: {failures.error.message}</Notice>
      {/if}
      {#if failures.data}
        <DataTable
          label="Latest failures in {label}, newest first"
          rows={failureRows}
          columns={failureColumns}
          rowKey={(e) => e.key}
          onRowClick={(e) => openGatePanel(e, open !== null)}
          rowLabel={(e) => `${e.name} failed ${formatRelative(e.ts, clock.now)}. Open gate`}
          busy={failures.loading}
        >
          {#snippet empty()}
            <EmptyState title={emptyTitle("failures", scopeText)} />
          {/snippet}
        </DataTable>
      {:else if failures.loading}
        <p class="loading" aria-live="polite">Loading failures</p>
      {/if}
    </section>
  {/if}
</section>

{#if open}
  <GateDetail
    repo={open.repo}
    name={open.name}
    onclose={() => closeGatePanel(openKey, { page: "repo", repo })}
  />
{/if}

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .head {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .back {
    align-self: flex-start;
    font-size: var(--text-sm);
  }

  .title-row {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-3);
  }

  .titles {
    min-width: 0;
  }

  .page-title {
    overflow-wrap: anywhere;
  }

  .path {
    margin: 2px 0 0;
    color: var(--text-muted);
    overflow-wrap: anywhere;
  }

  .panel {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
  }

  .gate {
    font-weight: 500;
  }

  .loading {
    margin: 0;
    color: var(--text-muted);
  }
</style>
