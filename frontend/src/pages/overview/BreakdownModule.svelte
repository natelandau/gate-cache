<!--
  @component
  Breakdown: a bar per repo, gate, source, branch, or machine for the selected range. A select
  picks the grouping, and clicking a column header sorts by it; the bars measure the sorted
  column. Repo rows cover every repo, dim the
  ones outside the repo filter, and filter to a repo on click. Other groupings follow the repo
  filter: a gate opens its panel, and any other row opens Activity filtered to its runs.

  Props:
  - `repoLabel`: the repo selection's display name, or null for all repos
  - `span`: page-local days the overview is scoped to, if any; row links carry them
-->
<script lang="ts">
  import { TERMS } from "../../lib/terms";
  import { getBreakdown, spanScope, type BreakdownRow } from "../../lib/api";
  import { barMetric, breakdownBars, DEFAULT_SORT, drillDown, type BreakdownSort, type Metric } from "../../lib/breakdown";
  import { METRIC_COLORS } from "../../lib/heat";
  import { nextSort } from "../../lib/table";
  import BarList, { type Bar } from "../../lib/components/BarList.svelte";
  import Button from "../../lib/components/Button.svelte";
  import Module from "../../lib/components/Module.svelte";
  import Select from "../../lib/components/Select.svelte";
  import { formatCount, formatDuration, formatPercent } from "../../lib/format";
  import { openGatePanel } from "../../lib/panel";
  import { dimension, DIMENSIONS, type Dimension } from "../../lib/dimensions";
  import { createQuery } from "../../lib/query.svelte";
  import { navigate } from "../../lib/router.svelte";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import type { DaySpan } from "../../lib/selection";
  import { filters, freshness, setRepos } from "../../lib/state.svelte";

  interface Props {
    repoLabel: string | null;
    span?: DaySpan;
  }

  let { repoLabel, span }: Props = $props();

  /** Rows shown before "Show all", so a long branch list stays a panel. */
  const VISIBLE = 15;

  let group = $state<Dimension>("repo");
  let sort = $state<BreakdownSort>(DEFAULT_SORT);
  let expanded = $state(false);

  const info = $derived(dimension(group));

  // A grouping that covers every repo ignores the repo filter, so only the others reload on it.
  const query = createQuery(
    (signal) => getBreakdown(group, { signal, scope: spanScope(span, info.allRepos ? [] : undefined) }),
    () => [group, info.allRepos ? null : filters.repos, span],
    { repos: false },
  );
  // The previous grouping's rows stay in `query.data` until the new load lands, and they must
  // not be drawn or clicked under the new grouping.
  const rows = $derived(query.data?.by === group ? query.data.rows : undefined);

  const groupOptions = DIMENSIONS.map((d) => ({ value: d.value, label: d.label }));

  // Time saved bars are green and failure bars red; every other measure is blue.
  const BAR_COLORS: Partial<Record<Metric, string>> = { saved: METRIC_COLORS.saved, fails: METRIC_COLORS.fail };

  // `gateOnly` columns describe one gate's passes, so only gate rows show them; `manyGates`
  // counts the gates in a row, so gate rows hide it.
  const allColumns: { key: Metric; label: string; text: (row: BreakdownRow) => string; gateOnly?: true; manyGates?: true }[] = [
    { key: "spent", label: TERMS.ran.column, text: (row) => formatDuration(row.time_spent) },
    { key: "saved", label: TERMS.saved.column, text: (row) => formatDuration(row.time_saved) },
    { key: "avg", label: "Avg run", text: (row) => formatDuration(row.avg_run), gateOnly: true },
    { key: "median", label: "Median run", text: (row) => formatDuration(row.median_run), gateOnly: true },
    { key: "runs", label: TERMS.calls.column, text: (row) => formatCount(row.runs) },
    { key: "skip", label: TERMS.skipRate.column, text: (row) => formatPercent(row.skip_rate) },
    { key: "fails", label: "Failures", text: (row) => formatCount(row.failures) },
    { key: "gates", label: "Gates", text: (row) => formatCount(row.gates), manyGates: true },
  ];

  const columns = $derived(allColumns.filter((c) => (info.oneGate ? !c.manyGates : !c.gateOnly)));
  const bars = $derived(breakdownBars(rows ?? [], sort, group, filters.repos));
  const barColor = $derived(BAR_COLORS[barMetric(sort)] ?? METRIC_COLORS.runs);

  // A first click sorts numbers largest first and names A to Z; a second click reverses.
  function sortBy(key: BreakdownSort["key"]): void {
    sort = nextSort(sort, key, key === "name" ? "asc" : "desc");
  }
  const shown = $derived(expanded ? bars : bars.slice(0, VISIBLE));
  const scope = $derived({ range: filters.range, span, repoLabel: info.allRepos ? null : repoLabel });

  function pickGroup(value: string): void {
    group = value as Dimension;
    expanded = false;
    // A grouping without the sorted column falls back to the default sort.
    if (sort.key !== "name" && !columns.some((c) => c.key === sort.key)) sort = DEFAULT_SORT;
  }

  function pick(bar: Bar<BreakdownRow>): void {
    const action = drillDown(group, bar.row);
    if (action.kind === "repo") setRepos([action.repo]);
    else if (action.kind === "gate") openGatePanel(action);
    else navigate({ ...action.route, ...(span ? { span } : {}) });
  }
</script>

<Module
  title="Breakdown"
  titleId="breakdown-title"
  loading={!rows && !query.error}
  error={query.error}
  empty={!rows || rows.length === 0}
  emptyTitle={emptyTitle("gate calls", scope)}
  emptyDetail={emptyHint({ ...scope, recording: freshness.recording })}
>
  {#snippet actions()}
    <span class="note">{info.allRepos ? "All repos, click a name to filter" : "Click a name for its runs"}</span>
    <Select label="Group by" value={group} options={groupOptions} onchange={pickGroup} />
  {/snippet}
  <BarList
    label="Breakdown by {info.label.toLowerCase()}"
    heading={info.label}
    rows={shown}
    color={barColor}
    {columns}
    onpick={pick}
    {sort}
    onsort={sortBy}
    widths={{ name: "160px", bar: "24%" }}
  />
  {#if bars.length > VISIBLE}
    <div class="more">
      <Button onclick={() => (expanded = !expanded)}>
        {expanded ? `Show top ${VISIBLE}` : `Show all ${formatCount(bars.length)}`}
      </Button>
    </div>
  {/if}
</Module>

<style>
  .note {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }

  .more {
    display: flex;
    justify-content: center;
    padding-top: var(--space-2);
  }
</style>
