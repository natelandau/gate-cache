<!--
  @component
  Why gates ran uncached: each reason a run skipped the cache, with its count and a neutral
  bar scaled to the most common reason. A row opens Activity filtered to that outcome and
  reason.

  Props:
  - `repoLabel`: the repo selection's display name, or null for all repos
  - `span`: page-local days the overview is scoped to, if any
-->
<script lang="ts">
  import { getReasons, spanScope, type ReasonRow } from "../../lib/api";
  import Module from "../../lib/components/Module.svelte";
  import { OUTCOMES } from "../../lib/events";
  import { formatCount } from "../../lib/format";
  import { createQuery } from "../../lib/query.svelte";
  import { activityHref } from "../../lib/router.svelte";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import type { DaySpan } from "../../lib/selection";
  import { filters, freshness } from "../../lib/state.svelte";

  interface Props {
    repoLabel: string | null;
    /** Page-local days the overview is scoped to. */
    span?: DaySpan;
  }

  let { repoLabel, span }: Props = $props();

  const query = createQuery(
    (signal) => getReasons({ signal, scope: spanScope(span) }),
    () => span,
  );

  const rows = $derived(query.data ?? []);
  const max = $derived(Math.max(0, ...rows.map((row) => row.count)));

  function runsText(row: ReasonRow): string {
    return `${OUTCOMES[row.outcome].label}: ${formatCount(row.count)} ${row.count === 1 ? "run" : "runs"}`;
  }
</script>

<Module
  title="Why gates ran uncached"
  titleId="reasons-title"
  noun="reasons"
  loading={query.loading && !query.data}
  error={query.error}
  empty={!query.data || query.data.length === 0}
  emptyTitle={emptyTitle("uncached runs", { range: filters.range, span, repoLabel })}
  emptyDetail={emptyHint({ range: filters.range, span, repoLabel, recording: freshness.recording })}
>
  <ul class="reasons">
    {#each rows as row (`${row.outcome}:${row.reason}`)}
      <li>
        <a
          class="row"
          href={activityHref({ outcome: row.outcome, reason: row.reason }, span)}
          title={runsText(row)}
        >
          <span class="reason"
            >{row.reason}<span class="visually-hidden"> ({OUTCOMES[row.outcome].label})</span></span
          >
          <span class="track" aria-hidden="true">
            <span class="fill" style:width="{max > 0 ? (row.count / max) * 100 : 0}%"></span>
          </span>
          <span class="count mono">{formatCount(row.count)}</span>
        </a>
      </li>
    {/each}
  </ul>
</Module>

<style>
  .reasons {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    border-bottom: 1px solid var(--border);
  }

  li:last-child {
    border-bottom: 0;
  }

  .row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 80px 40px;
    gap: 10px;
    align-items: center;
    height: var(--row-height);
    padding: 0 var(--space-2);
    color: var(--text);
    text-decoration: none;
  }

  .row:hover {
    background: var(--surface-hover);
  }

  .row:hover .reason {
    text-decoration: underline;
  }

  /* Inset so the ring stays inside the list instead of overlapping the next row. */
  .row:focus-visible {
    outline-offset: -2px;
  }

  .reason {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .track {
    display: block;
    height: 12px;
    border-radius: 2px;
    background: var(--surface-sunken);
    overflow: hidden;
  }

  .fill {
    display: block;
    height: 100%;
    border-radius: 2px;
    background: var(--chart-neutral);
  }

  .count {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
</style>
