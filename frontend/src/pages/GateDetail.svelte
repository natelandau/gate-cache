<!--
  @component
  One gate's detail as a panel over the Gates table: headline numbers, the pass duration
  trend, the latest runs, and flaky trees. Escape anywhere or the close button closes it.
  On narrow screens it covers the page as a modal sheet and the rest of the page is inert.

  Props:
  - `repo`, `name`: the gate, with `repo` its own repo (null when recorded without one)
  - `onclose`: close the panel
-->
<script lang="ts">
  import {
    getGate,
    getGates,
    type EventRow,
    type FlakyTree,
    type GateDetail,
    type GateRow,
  } from "../lib/api";
  import Badge from "../lib/components/Badge.svelte";
  import Button from "../lib/components/Button.svelte";
  import DataTable, { type Column } from "../lib/components/DataTable.svelte";
  import EmptyState from "../lib/components/EmptyState.svelte";
  import Notice from "../lib/components/Notice.svelte";
  import OutcomeBadge from "../lib/components/OutcomeBadge.svelte";
  import StatStrip, { type Stat } from "../lib/components/StatStrip.svelte";
  import TrendChart from "../lib/components/TrendChart.svelte";
  import { eventKeys, eventTitle, shortTree, timeText } from "../lib/events";
  import { formatCount, formatDuration, formatPercent, formatRelative, formatTimestamp } from "../lib/format";
  import { findGate } from "../lib/gates";
  import { inertOutside } from "../lib/inert";
  import { createQuery } from "../lib/query.svelte";
  import { emptyTitle } from "../lib/scope";
  import { clock, filters } from "../lib/state.svelte";

  interface Props {
    repo: string | null;
    name: string;
    onclose: () => void;
  }

  let { repo, name, onclose }: Props = $props();

  // The gate's totals come from the gates list scoped to its own repo, so they show even when
  // the global repo filter hides the gate from the table.
  const query = createQuery(
    async (signal): Promise<{ detail: GateDetail; row: GateRow | undefined }> => {
      const gate = { repo, name };
      // The totals are extra: when they fail to load, the detail still shows without them.
      const [detail, rows] = await Promise.allSettled([
        getGate(name, repo, { signal }),
        getGates({ signal, repo }),
      ]);
      if (detail.status === "rejected") throw detail.reason;
      return {
        detail: detail.value,
        row: rows.status === "fulfilled" ? findGate(rows.value, gate) : undefined,
      };
    },
    () => [repo, name],
  );

  const detail = $derived(query.data?.detail);
  const row = $derived(query.data?.row);

  let panel: HTMLElement;

  // Focus the panel on open and when it switches gates, so keyboard users land in it.
  $effect(() => {
    void [repo, name];
    panel.focus();
  });

  const SHEET_QUERY = "(max-width: 720px)";
  let narrow = $state(false);

  $effect(() => {
    const media = matchMedia(SHEET_QUERY);
    const update = () => {
      narrow = media.matches;
    };
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  });

  $effect(() => {
    if (narrow) return inertOutside(panel);
  });

  function onWindowKeydown(event: KeyboardEvent): void {
    if (event.key !== "Escape" || event.defaultPrevented) return;
    // Escape in a form control belongs to the control, such as closing a select.
    if (event.target instanceof Element && event.target.closest("input, select, textarea")) return;
    event.preventDefault();
    onclose();
  }

  const stats = $derived.by((): Stat[] => {
    if (!row) return [];
    return [
      {
        label: "Runs",
        value: formatCount(row.runs),
        hint: `${formatCount(row.failures)} ${row.failures === 1 ? "failure" : "failures"}`,
      },
      { label: "Skip rate", value: formatPercent(row.skip_rate) },
      {
        label: "Avg run",
        value: formatDuration(row.avg_run),
        hint: row.median_run === null ? undefined : `median ${formatDuration(row.median_run)}`,
      },
      { label: "Saved", value: formatDuration(row.time_saved) },
    ];
  });

  type Recent = EventRow & { key: string };
  const recent = $derived.by<Recent[]>(() => {
    const events = detail?.recent ?? [];
    const keys = eventKeys(events);
    return events.map((event, index) => ({ ...event, key: keys[index]! }));
  });

  const recentColumns: Column<Recent>[] = [
    {
      key: "ts",
      label: "When",
      cell: when,
      title: (e) => formatTimestamp(e.ts),
    },
    { key: "outcome", label: "Outcome", cell: outcome },
    { key: "time", label: "Time", sortable: false, text: timeText },
    {
      key: "tree",
      label: "Tree",
      cell: tree,
      title: (e) => e.tree ?? undefined,
    },
  ];

  const treeColumns: Column<FlakyTree>[] = [
    { key: "tree", label: "Tree", cell: flakyTree, title: (t) => t.tree },
    { key: "fails", label: "Fails", align: "right", text: (t) => formatCount(t.fails) },
    { key: "passes", label: "Passes", align: "right", text: (t) => formatCount(t.passes) },
    {
      key: "last",
      label: "Last seen",
      align: "right",
      text: (t) => formatRelative(t.last, clock.now),
      title: (t) => formatTimestamp(t.last),
    },
  ];
</script>

{#snippet when(e: Recent)}{formatRelative(e.ts, clock.now)}{/snippet}
{#snippet outcome(e: Recent)}<OutcomeBadge outcome={e.outcome} title={eventTitle(e)} />{/snippet}
{#snippet tree(e: Recent)}<span class="mono">{shortTree(e.tree)}</span>{/snippet}
{#snippet flakyTree(t: FlakyTree)}<span class="mono">{shortTree(t.tree)}</span>{/snippet}

<svelte:window onkeydown={onWindowKeydown} />

<div
  class="panel"
  role="dialog"
  aria-modal={narrow}
  aria-labelledby="gate-title"
  tabindex="-1"
  bind:this={panel}
>
  <header class="head">
    <div class="titles">
      <h2 id="gate-title" class="title">
        {name}
        {#if row?.flaky}<Badge tone="flaky" title="A tree both failed and passed">flaky</Badge>{/if}
      </h2>
      <p class="repo" title={repo ?? undefined}>{detail?.repo_name ?? ""}</p>
    </div>
    <Button square label="Close gate details" onclick={onclose}>
      <span aria-hidden="true">✕</span>
    </Button>
  </header>

  <div class="content" aria-busy={query.loading}>
    {#if query.error}
      <Notice tone="error">Could not load this gate: {query.error.message}</Notice>
    {/if}

    {#if stats.length}
      <StatStrip {stats} busy={query.loading} />
    {/if}

    {#if detail}
      {#if detail.recent.length === 0}
        <EmptyState
          title={emptyTitle(`runs of ${name}`, { range: filters.range, repoLabel: null })}
          detail="Pick a longer range to see older runs."
        />
      {:else}
        <section>
          <h3 class="section-title">Pass duration</h3>
          {#if detail.trend.length}
            <TrendChart trend={detail.trend} />
          {:else}
            <p class="muted">No passes with a recorded duration in this range.</p>
          {/if}
        </section>

        {#if detail.flaky_trees.length}
          <section>
            <h3 class="section-title">Flaky trees</h3>
            <DataTable
              label="Flaky trees of {name}"
              rows={detail.flaky_trees}
              columns={treeColumns}
              rowKey={(t) => t.tree}
              busy={query.loading}
            />
          </section>
        {/if}

        <section>
          <h3 class="section-title">
            Latest {formatCount(recent.length)}
            {recent.length === 1 ? "run" : "runs"}
          </h3>
          <DataTable
            label="Latest runs of {name}"
            rows={recent}
            columns={recentColumns}
            rowKey={(e) => e.key}
            busy={query.loading}
          />
        </section>
      {/if}
    {:else if query.loading}
      <p class="muted" aria-live="polite">Loading gate</p>
    {/if}
  </div>
</div>

<style>
  .panel {
    position: fixed;
    /* App measures the sticky top bar, which grows when its controls wrap. */
    top: var(--topbar-offset, var(--topbar-height));
    right: 0;
    bottom: 0;
    z-index: 5;
    width: min(560px, 100vw);
    display: flex;
    flex-direction: column;
    background: var(--bg);
    border-left: 1px solid var(--border-strong);
    box-shadow: var(--shadow-panel);
  }

  .panel:focus {
    outline: none;
  }

  .panel:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: -2px;
  }

  .head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }

  .titles {
    min-width: 0;
  }

  .title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-lg);
    overflow-wrap: anywhere;
  }

  .repo {
    margin: 2px 0 0;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  .content {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-4);
  }

  .muted {
    margin: 0;
    color: var(--text-muted);
  }

  /* The top bar wraps to a variable height here, so the panel covers the whole screen. */
  @media (max-width: 720px) {
    .panel {
      top: 0;
      z-index: 7;
      border-left: 0;
    }
  }
</style>
