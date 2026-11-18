<!--
  @component
  One gate's detail as a panel over the Gates table or the overview: headline numbers, the pass duration
  trend, the latest runs, and flaky trees. Escape anywhere or the close button closes it.
  On narrow screens it covers the page as a modal sheet and the rest of the page is inert.

  Props:
  - `repo`, `name`: the gate, with `repo` its own repo (null when recorded without one)
  - `onclose`: close the panel
-->
<script lang="ts">
  import { TERMS } from "../lib/terms";
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
  import GateName from "../lib/components/GateName.svelte";
  import Notice from "../lib/components/Notice.svelte";
  import OutcomeBadge from "../lib/components/OutcomeBadge.svelte";
  import RunHistogram from "../lib/components/RunHistogram.svelte";
  import ShareMix from "../lib/components/ShareMix.svelte";
  import StatStrip, { type Stat } from "../lib/components/StatStrip.svelte";
  import TrendChart from "../lib/components/TrendChart.svelte";
  import Icon from "../lib/components/Icon.svelte";
  import { eventKeys, eventTitle, ranText, savedText, shortTree } from "../lib/events";
  import TimeValue from "../lib/components/TimeValue.svelte";
  import {
    formatBytes,
    formatCount,
    formatDuration,
    formatPercent,
    formatRatio,
    formatRelative,
    formatTimestamp,
  } from "../lib/format";
  import { findGate, sourceParts } from "../lib/gates";
  import { inertOutside } from "../lib/inert";
  import { createQuery } from "../lib/query.svelte";
  import { UNKNOWN_REPO } from "../lib/router.svelte";
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
        getGates({ signal, repos: [repo ?? UNKNOWN_REPO] }),
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
      { label: TERMS.calls.label, value: formatCount(row.runs) },
      {
        label: "Avg run",
        value: formatDuration(row.avg_run),
        hint: runHint(row),
      },
      {
        label: TERMS.ran.column,
        value: formatDuration(row.time_spent),
        hint: row.fail_time ? `${formatDuration(row.fail_time)} lost to failures` : undefined,
      },
      {
        label: "Failures",
        value: formatCount(row.failures),
        tone: row.failures ? "danger" : "default",
      },
      { label: "CPU/wall", value: formatRatio(row.cpu_ratio) },
      {
        label: "Peak memory",
        value: formatBytes(row.peak_rss),
        hint: row.median_rss === null ? undefined : `median ${formatBytes(row.median_rss)}`,
      },
      { label: TERMS.skipRate.label, value: formatPercent(row.skip_rate) },
      { label: TERMS.saved.column, value: formatDuration(row.time_saved) },
    ];
  });

  function runHint(r: GateRow): string | undefined {
    const parts: string[] = [];
    if (r.median_run !== null) parts.push(`median ${formatDuration(r.median_run)}`);
    if (r.p90_run !== null) parts.push(`p90 ${formatDuration(r.p90_run)}`);
    return parts.length ? parts.join(" \u00b7 ") : undefined;
  }

  // Failures are counted from the timing classes, the same data the section shows.
  const failureClasses = $derived.by(() => {
    const timing = detail?.failure_timing;
    if (!timing) return [];
    const threshold = timing.threshold === null ? "" : ` (${formatDuration(timing.threshold)})`;
    return [
      {
        key: "early",
        label: "Early",
        title: `Early: ended before half of the median passing run${threshold}`,
        ...timing.early,
      },
      {
        key: "late",
        label: "Late",
        title: `Late: ran at least half of the median passing run${threshold}`,
        ...timing.late,
      },
      {
        key: "unclassified",
        label: "Unclassified",
        title: "No passing run with a duration to compare against",
        ...timing.unclassified,
      },
    ].filter((c) => c.runs > 0);
  });

  const sources = $derived(sourceParts(detail?.by_source ?? []));

  type Recent = EventRow & { key: string };
  const recent = $derived.by<Recent[]>(() => {
    const events = detail?.recent ?? [];
    const keys = eventKeys(events);
    return events.map((event, index) => ({ ...event, key: keys[index]! }));
  });

  // A gate whose runs used a key, such as "test@v22", shows which key each run used.
  const keyed = $derived(recent.some((e) => e.name !== e.gate));
  const recentColumns: Column<Recent>[] = $derived([
    {
      key: "ts",
      label: "When",
      cell: when,
      title: (e) => formatTimestamp(e.ts),
    },
    ...(keyed
      ? [{ key: "name", label: "Name", sortable: false, cell: runName, title: (e: Recent) => e.name }]
      : []),
    { key: "outcome", label: "Outcome", cell: outcome },
    { key: "ran", label: "Ran for", sortable: false, align: "right", cell: ranCell },
    { key: "saved", label: TERMS.saved.column, sortable: false, align: "right", cell: savedCell },
    {
      key: "tree",
      label: "Tree",
      cell: tree,
      title: (e) => e.tree ?? undefined,
    },
  ]);

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

{#snippet ranCell(e: EventRow)}<TimeValue value={ranText(e)} />{/snippet}
{#snippet savedCell(e: EventRow)}<TimeValue value={savedText(e)} />{/snippet}

{#snippet when(e: Recent)}{formatRelative(e.ts, clock.now)}{/snippet}
{#snippet outcome(e: Recent)}<OutcomeBadge outcome={e.outcome} title={eventTitle(e)} />{/snippet}
{#snippet runName(e: Recent)}<GateName name={e.name} gate={e.gate} />{/snippet}
{#snippet tree(e: Recent)}{shortTree(e.tree)}{/snippet}
{#snippet flakyTree(t: FlakyTree)}{shortTree(t.tree)}{/snippet}

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
      <Icon name="x" />
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
          title={emptyTitle(`calls of ${name}`, { range: filters.range, repoLabel: null })}
          detail="Pick a longer range to see older runs."
        />
      {:else}
        <section>
          <h3 class="section-title">Passing run time</h3>
          {#if detail.trend.length}
            <TrendChart trend={detail.trend} />
          {:else}
            <p class="muted">No passes with a recorded duration in this range.</p>
          {/if}
        </section>

        <section>
          <h3 class="section-title">Run time spread</h3>
          {#if detail.histogram}
            <RunHistogram histogram={detail.histogram} />
          {:else}
            <p class="muted">Needs 5 passing runs</p>
          {/if}
        </section>

        {#if failureClasses.length}
          <section>
            <h3 class="section-title">Failures</h3>
            <ul class="failures">
              {#each failureClasses as c (c.key)}
                <li title={c.title}>
                  <span>{c.label}</span>
                  <span class="num">{formatCount(c.runs)} {c.runs === 1 ? "run" : "runs"}</span>
                  <span class="num muted">{formatDuration(c.time)}</span>
                </li>
              {/each}
            </ul>
          </section>
        {/if}

        {#if sources.length}
          <section>
            <h3 class="section-title">Time ran by source</h3>
            <ShareMix parts={sources} format={formatDuration} />
          </section>
        {/if}

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
            {recent.length === 1 ? "call" : "calls"}
          </h3>
          <DataTable
            label="Latest calls of {name}"
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
    border-left: 1px solid var(--border);
    box-shadow: var(--shadow-panel);
    animation: panel-in var(--dur-slow) var(--ease);
  }

  @keyframes panel-in {
    from {
      opacity: 0;
      transform: translateX(16px);
    }
    to {
      opacity: 1;
      transform: none;
    }
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
    padding: var(--space-4) var(--space-5);
    border-bottom: 1px solid var(--border);
    background: var(--bg);
  }

  .titles {
    min-width: 0;
  }

  .title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-lg);
    font-weight: 600;
    letter-spacing: var(--track-lg);
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
    gap: var(--space-5);
    padding: var(--space-5);
  }

  .muted {
    margin: 0;
    color: var(--text-muted);
  }

  .failures {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    gap: var(--space-1) var(--space-3);
    margin: 0;
    padding: 0;
    font-size: var(--text-sm);
    list-style: none;
  }

  .failures li {
    display: grid;
    grid-column: 1 / -1;
    grid-template-columns: subgrid;
  }

  .num {
    text-align: right;
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
