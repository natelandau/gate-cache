<script lang="ts">
  import { getRepos, type RepoRow } from "../lib/api";
  import DataTable, { type Column, type SortState } from "../lib/components/DataTable.svelte";
  import EmptyState from "../lib/components/EmptyState.svelte";
  import Notice from "../lib/components/Notice.svelte";
  import { formatCount, formatDuration, formatPercent } from "../lib/format";
  import { createQuery } from "../lib/query.svelte";
  import { navigate } from "../lib/router.svelte";
  import { emptyHint, emptyTitle } from "../lib/scope";
  import { filters, freshness } from "../lib/state.svelte";

  interface Props {
    repoLabel: string | null;
  }

  let { repoLabel }: Props = $props();

  const query = createQuery((signal) => getRepos({ signal }));

  let sort: SortState | null = $state({ key: "time_saved", direction: "desc" });

  const columns: Column<RepoRow>[] = [
    {
      key: "repo_name",
      label: "Repo",
      title: (r) => r.repo ?? "Runs recorded outside a git repo; they have no repo page",
    },
    { key: "runs", label: "Runs", align: "right", text: (r) => formatCount(r.runs) },
    { key: "skip_rate", label: "Skip %", align: "right", text: (r) => formatPercent(r.skip_rate) },
    { key: "time_saved", label: "Saved", align: "right", text: (r) => formatDuration(r.time_saved) },
    { key: "failures", label: "Failures", align: "right", cell: failuresCell },
    { key: "gates", label: "Gates", align: "right", text: (r) => formatCount(r.gates) },
  ];

  function select(row: RepoRow): void {
    if (row.repo !== null) navigate({ page: "repo", repo: row.repo });
  }
</script>

{#snippet failuresCell(r: RepoRow)}
  <span class:danger={r.failures > 0}>{formatCount(r.failures)}</span>
{/snippet}

<section class="page" aria-labelledby="repos-title">
  <h1 id="repos-title" class="page-title">Repos</h1>

  {#if query.error}
    <Notice tone="error">Could not load repos: {query.error.message}</Notice>
  {/if}

  {#if query.data}
    <DataTable
      label="Repos"
      rows={query.data}
      {columns}
      bind:sort
      rowKey={(r) => r.repo ?? ""}
      onRowClick={select}
      canActivate={(r) => r.repo !== null}
      rowLabel={(r) => `Open ${r.repo_name}`}
      busy={query.loading}
    >
      {#snippet empty()}
        <EmptyState
          title={emptyTitle("runs", { range: filters.range, repoLabel })}
          detail={emptyHint({ range: filters.range, repoLabel, recording: freshness.recording })}
        />
      {/snippet}
    </DataTable>
    {#if query.data.length}
      <p class="hint">Select a repo to see its gates and recent failures.</p>
    {/if}
  {:else if query.loading}
    <p class="loading" aria-live="polite">Loading repos</p>
  {/if}
</section>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .danger {
    color: var(--danger);
  }

  .hint {
    margin: calc(-1 * var(--space-2)) 0 0;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  .loading {
    margin: 0;
    color: var(--text-muted);
  }
</style>
