<!--
  @component
  Breakdown: a bar per repo, gate, source, branch, or machine for the selected range. A select
  picks the grouping and tabs pick what the bars measure. Repo rows cover every repo, dim the
  ones outside the repo filter, and filter to a repo on click. Other groupings follow the repo
  filter: a gate opens its panel, and any other row opens Activity filtered to its runs.

  Props:
  - `repoLabel`: the repo selection's display name, or null for all repos
  - `span`: page-local days the overview is scoped to, if any; row links carry them
-->
<script lang="ts">
  import { getBreakdown, spanScope, type BreakdownRow } from "../../lib/api";
  import { breakdownBars, drillDown, type Metric } from "../../lib/breakdown";
  import BarList, { type Bar } from "../../lib/components/BarList.svelte";
  import Button from "../../lib/components/Button.svelte";
  import MetricTabs from "../../lib/components/MetricTabs.svelte";
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
  let by = $state<Metric>("saved");
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

  const options: { value: Metric; label: string }[] = [
    { value: "saved", label: "Time saved" },
    { value: "spent", label: "Time spent" },
    { value: "runs", label: "Runs" },
    { value: "skip", label: "Skip %" },
    { value: "fails", label: "Failures" },
  ];

  const COLORS: Record<Metric, "saved" | "runs" | "fails"> = {
    saved: "saved",
    spent: "runs",
    runs: "runs",
    skip: "runs",
    fails: "fails",
  };

  const allColumns: { label: string; text: (row: BreakdownRow) => string }[] = [
    { label: "Saved", text: (row) => formatDuration(row.time_saved) },
    { label: "Spent", text: (row) => formatDuration(row.time_spent) },
    { label: "Avg", text: (row) => formatDuration(row.avg_run) },
    { label: "Median", text: (row) => formatDuration(row.median_run) },
    { label: "Runs", text: (row) => formatCount(row.runs) },
    { label: "Skip %", text: (row) => formatPercent(row.skip_rate) },
    { label: "Failures", text: (row) => formatCount(row.failures) },
    { label: "Gates", text: (row) => formatCount(row.gates) },
  ];

  // Avg and median describe one gate's passes, so only gate rows show them.
  const GATE_ONLY = new Set(["Avg", "Median"]);
  const columns = $derived(
    allColumns.filter((c) => {
      if (c.label === "Gates") return !info.oneGate;
      if (GATE_ONLY.has(c.label)) return info.oneGate;
      return true;
    }),
  );
  const bars = $derived(breakdownBars(rows ?? [], by, group, filters.repos));
  const shown = $derived(expanded ? bars : bars.slice(0, VISIBLE));
  const scope = $derived({ range: filters.range, span, repoLabel: info.allRepos ? null : repoLabel });

  function pickGroup(value: string): void {
    group = value as Dimension;
    expanded = false;
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
  emptyTitle={emptyTitle("runs", scope)}
  emptyDetail={emptyHint({ ...scope, recording: freshness.recording })}
>
  {#snippet actions()}
    <span class="note">{info.allRepos ? "All repos, click a name to filter" : "Click a name for its runs"}</span>
    <Select label="Group by" value={group} options={groupOptions} onchange={pickGroup} />
    <MetricTabs
      label="Measure groups by"
      {options}
      value={by}
      onchange={(v) => (by = v as Metric)}
    />
  {/snippet}
  <BarList
    label="Runs by {info.label.toLowerCase()}"
    heading={info.label}
    rows={shown}
    color={COLORS[by]}
    {columns}
    onpick={pick}
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
