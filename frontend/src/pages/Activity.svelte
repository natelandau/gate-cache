<script lang="ts">
  import GateName from "../lib/components/GateName.svelte";
  import { TERMS } from "../lib/terms";
  import { tick } from "svelte";
  import {
    activityHint,
    activitySubject,
    addPage,
    feedView,
    filterParts,
    PAGE_SIZE,
    type FilterPart,
    type PagedFeed,
  } from "../lib/activity";
  import { getActivity, spanScope, type ActivityFilter, type EventRow, type Outcome } from "../lib/api";
  import Button from "../lib/components/Button.svelte";
  import DataTable, { type Column } from "../lib/components/DataTable.svelte";
  import EmptyState from "../lib/components/EmptyState.svelte";
  import FilterChip from "../lib/components/FilterChip.svelte";
  import Notice from "../lib/components/Notice.svelte";
  import OutcomeBadge from "../lib/components/OutcomeBadge.svelte";
  import Select from "../lib/components/Select.svelte";
  import { eventKeys, eventTitle, OUTCOMES, ranText, savedText } from "../lib/events";
  import TimeValue from "../lib/components/TimeValue.svelte";
  import PageHeader from "../lib/components/PageHeader.svelte";
  import { formatCount, formatRelative, formatTimestamp } from "../lib/format";
  import { createQuery } from "../lib/query.svelte";
  import { navigate } from "../lib/router.svelte";
  import { emptyTitle, scopeSubtitle } from "../lib/scope";
  import { clock, filters, freshness } from "../lib/state.svelte";

  interface Props {
    repoLabel: string | null;
    /** The page-local filters from the hash route. */
    filter: ActivityFilter;
  }

  let { repoLabel, filter }: Props = $props();

  function fetchPage(before: string | null, signal: AbortSignal) {
    const { span, ...rest } = filter;
    return getActivity({ limit: PAGE_SIZE, before, ...rest }, { signal, scope: spanScope(span) });
  }

  // The first page follows the archive live; see lib/activity.ts for why later pages do not.
  const first = createQuery((signal) => fetchPage(null, signal), () => filter);

  const outcomeOptions = [
    { value: "", label: "All outcomes" },
    ...Object.entries(OUTCOMES).map(([value, { label }]) => ({ value, label })),
  ];

  // Filter changes replace the history entry, so going back leaves the page instead of
  // stepping through every filter tried.
  function show(next: ActivityFilter): void {
    navigate({ page: "activity", ...next }, { replace: true });
  }

  function showOutcome(value: string): void {
    const { outcome: _, ...rest } = filter;
    show(value ? { ...rest, outcome: value as Outcome } : rest);
  }

  const parts = $derived(filterParts(filter));

  function remove(part: FilterPart): void {
    show(part.without);
    heading?.focus();
  }

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

  // Pages loaded under other filters never mix with the first page of the current ones.
  const inputs = $derived(JSON.stringify([filters.repos, filters.range, filter]));

  $effect(() => {
    void inputs;
    resetPaging();
  });
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
    { key: "name", label: "Gate", sortable: false, cell: gate, title: (e) => e.name },
    { key: "repo_name", label: "Repo", sortable: false, title: (e) => e.repo ?? undefined },
    { key: "outcome", label: "Outcome", sortable: false, cell: outcomeCell },
    { key: "ran", label: "Ran for", sortable: false, align: "right", cell: ranCell },
    { key: "saved", label: TERMS.saved.column, sortable: false, align: "right", cell: savedCell },
  ];

  let heading: HTMLElement | undefined = $state();
  const subtitle = $derived(scopeSubtitle(repoLabel, filters.range));

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
      const page = await fetchPage(before, controller.signal);
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
    heading?.focus();
    window.scrollTo({ top: 0 });
  }
</script>

{#snippet ranCell(e: EventRow)}<TimeValue value={ranText(e)} />{/snippet}
{#snippet savedCell(e: EventRow)}<TimeValue value={savedText(e)} />{/snippet}

{#snippet when(e: Row)}{formatRelative(e.ts, clock.now)}{/snippet}
{#snippet gate(e: Row)}<span class="gate"><GateName name={e.name} /></span>{/snippet}
{#snippet outcomeCell(e: Row)}<OutcomeBadge outcome={e.outcome} title={eventTitle(e)} />{/snippet}

<section class="page" aria-labelledby="activity-title">
  <div class="head">
    <PageHeader title="Activity" headingId="activity-title" {subtitle} bind:heading />
    {#if view.newer}
      <Button tone="accent" onclick={showLatest}>New runs. Show latest</Button>
    {/if}
  </div>

  <div class="filters">
    <Select label="Outcome" value={filter.outcome ?? ""} options={outcomeOptions} onchange={showOutcome} />
    {#each parts as part (part.key)}
      <FilterChip
        label={part.label}
        title={part.title}
        removeLabel="Remove {part.noun} filter"
        onremove={() => remove(part)}
      />
    {/each}
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
            title={emptyTitle(activitySubject(filter), { range: filters.range, span: filter.span, repoLabel })}
            detail={activityHint(
              filter,
              { range: filters.range, repoLabel, recording: freshness.recording },
            )}
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
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--space-3);
    min-height: var(--control-height);
  }

  .filters {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
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
