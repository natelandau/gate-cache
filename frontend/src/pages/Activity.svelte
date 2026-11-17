<script lang="ts">
  import { tick } from "svelte";
  import { addPage, feedView, PAGE_SIZE, type PagedFeed } from "../lib/activity";
  import { getActivity, type EventRow } from "../lib/api";
  import Button from "../lib/components/Button.svelte";
  import DataTable, { type Column } from "../lib/components/DataTable.svelte";
  import EmptyState from "../lib/components/EmptyState.svelte";
  import Notice from "../lib/components/Notice.svelte";
  import OutcomeBadge from "../lib/components/OutcomeBadge.svelte";
  import { eventKeys, eventTitle, OUTCOMES, timeText } from "../lib/events";
  import { formatCount, formatRelative, formatTimestamp } from "../lib/format";
  import { createQuery } from "../lib/query.svelte";
  import { navigate } from "../lib/router.svelte";
  import { emptyHint, emptyTitle } from "../lib/scope";
  import { clock, filters, freshness } from "../lib/state.svelte";

  interface Props {
    repoLabel: string | null;
  }

  let { repoLabel }: Props = $props();

  // The first page follows the archive live; see lib/activity.ts for why later pages do not.
  const first = createQuery((signal) => getActivity({ limit: PAGE_SIZE }, { signal }));

  let paged: PagedFeed | null = $state(null);
  let loadingMore = $state(false);
  let moreError: Error | undefined = $state();
  let moreController: AbortController | null = null;

  function resetPaging(): void {
    moreController?.abort();
    moreController = null;
    paged = null;
    loadingMore = false;
    moreError = undefined;
  }

  $effect(() => {
    void [filters.repo, filters.range];
    resetPaging();
  });

  // Pages loaded under other filters never mix with the first page of the current ones.
  const inputs = $derived(JSON.stringify([filters.repo, filters.range]));
  const view = $derived(feedView(first.data, paged, inputs));

  type Row = EventRow & { key: string };
  const rows = $derived.by<Row[]>(() => {
    const keys = eventKeys(view.events);
    return view.events.map((event, index) => ({ ...event, key: keys[index]! }));
  });

  const columns: Column<Row>[] = [
    {
      key: "ts",
      label: "When",
      sortable: false,
      cell: when,
      title: (e) => formatTimestamp(e.ts),
      width: "96px",
    },
    { key: "name", label: "Gate", sortable: false, cell: gate },
    { key: "repo_name", label: "Repo", sortable: false, title: (e) => e.repo ?? undefined },
    { key: "outcome", label: "Outcome", sortable: false, cell: outcome },
    { key: "time", label: "Time", sortable: false, align: "right", text: timeText },
  ];

  let heading: HTMLElement;

  async function loadMore(): Promise<void> {
    const live = first.data;
    const before = view.next;
    // While the first page reloads for new filters, its cursor belongs to the old ones.
    if (!live || !before || first.loading) return;
    const at = inputs;
    const shown = view.events.length;
    moreController?.abort();
    const controller = new AbortController();
    moreController = controller;
    loadingMore = true;
    moreError = undefined;
    try {
      const page = await getActivity({ limit: PAGE_SIZE, before }, { signal: controller.signal });
      if (controller.signal.aborted || inputs !== at) return;
      paged = addPage(paged, live, page, at);
      await tick();
      // Continue keyboard reading at the first newly loaded event.
      const key = rows[shown]?.key;
      if (key) document.querySelector<HTMLElement>(`#activity-feed tr[data-key="${CSS.escape(key)}"]`)?.focus();
    } catch (error) {
      if (!controller.signal.aborted) {
        moreError = error instanceof Error ? error : new Error(String(error));
      }
    } finally {
      if (moreController === controller) {
        loadingMore = false;
        moreController = null;
      }
    }
  }

  function showLatest(): void {
    resetPaging();
    heading.focus();
    window.scrollTo({ top: 0 });
  }
</script>

{#snippet when(e: Row)}{formatRelative(e.ts, clock.now)}{/snippet}
{#snippet gate(e: Row)}<span class="gate">{e.name}</span>{/snippet}
{#snippet outcome(e: Row)}<OutcomeBadge outcome={e.outcome} title={eventTitle(e)} />{/snippet}

<section class="page" aria-labelledby="activity-title">
  <div class="head">
    <h1 id="activity-title" class="page-title" tabindex="-1" bind:this={heading}>Activity</h1>
    {#if view.newer}
      <Button tone="accent" onclick={showLatest}>New runs. Show latest</Button>
    {/if}
  </div>

  {#if first.error}
    <Notice tone="error">Could not load activity: {first.error.message}</Notice>
  {/if}

  {#if first.data}
    <div id="activity-feed">
      <DataTable
        label="Runs, newest first"
        {rows}
        {columns}
        rowKey={(e) => e.key}
        onRowClick={(e) => navigate({ page: "gate", repo: e.repo, name: e.name })}
        rowLabel={(e) =>
          `${e.name} in ${e.repo_name}, ${OUTCOMES[e.outcome].label}, ${formatRelative(e.ts, clock.now)}. Open gate`}
        busy={first.loading}
      >
        {#snippet empty()}
          <EmptyState
            title={emptyTitle("runs", { range: filters.range, repoLabel })}
            detail={emptyHint({ range: filters.range, repoLabel, recording: freshness.recording })}
          />
        {/snippet}
      </DataTable>
    </div>

    {#if moreError}
      <Notice tone="error">Could not load more runs: {moreError.message}</Notice>
    {/if}

    {#if rows.length}
      <div class="foot">
        <span class="count">
          {formatCount(rows.length)}
          {rows.length === 1 ? "run" : "runs"}{view.next ? "" : ", end of range"}
        </span>
        {#if view.next}
          <Button onclick={loadMore} disabled={loadingMore || first.loading}>
            {loadingMore ? "Loading" : "Load more"}
          </Button>
        {/if}
      </div>
    {/if}
  {:else if first.loading}
    <p class="loading" aria-live="polite">Loading activity</p>
  {/if}
</section>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    min-height: var(--control-height);
  }

  .page-title:focus {
    outline: none;
  }

  .gate {
    font-weight: 500;
  }

  .foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    margin-top: calc(-1 * var(--space-2));
  }

  .count {
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  .loading {
    margin: 0;
    color: var(--text-muted);
  }
</style>
