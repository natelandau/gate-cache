<!--
  @component
  Repos: a bar per repo for the selected range, whatever the repo filter selects. Tabs pick
  what the bars measure. Repos outside the filter are dimmed, and clicking a name filters the
  dashboard to that repo.
-->
<script lang="ts">
  import { getRepos, type RepoRow } from "../../lib/api";
  import BarList from "../../lib/components/BarList.svelte";
  import MetricTabs from "../../lib/components/MetricTabs.svelte";
  import Module from "../../lib/components/Module.svelte";
  import { formatCount, formatDuration, formatPercent } from "../../lib/format";
  import { createQuery } from "../../lib/query.svelte";
  import { repoBars, type RepoMetric } from "../../lib/repobars";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import { filters, freshness, setRepos } from "../../lib/state.svelte";

  const query = createQuery(
    (signal) => getRepos({ signal, repos: [] }),
    () => null,
    { repos: false },
  );

  let by: RepoMetric = $state("saved");

  const options: { value: RepoMetric; label: string }[] = [
    { value: "saved", label: "Time saved" },
    { value: "runs", label: "Runs" },
    { value: "skip", label: "Skip %" },
    { value: "fails", label: "Failures" },
  ];

  const COLORS: Record<RepoMetric, "saved" | "runs" | "fails"> = {
    saved: "saved",
    runs: "runs",
    skip: "runs",
    fails: "fails",
  };

  const columns: { label: string; text: (row: RepoRow) => string }[] = [
    { label: "Saved", text: (row) => formatDuration(row.time_saved) },
    { label: "Runs", text: (row) => formatCount(row.runs) },
    { label: "Skip %", text: (row) => formatPercent(row.skip_rate) },
    { label: "Failures", text: (row) => formatCount(row.failures) },
    { label: "Gates", text: (row) => formatCount(row.gates) },
  ];

  const bars = $derived(repoBars(query.data ?? [], by, filters.repos));
</script>

<Module
  title="Repos"
  titleId="repos-title"
  loading={query.loading && !query.data}
  error={query.error}
  empty={!query.data || query.data.length === 0}
  emptyTitle={emptyTitle("runs", { range: filters.range, repoLabel: null })}
  emptyDetail={emptyHint({ range: filters.range, repoLabel: null, recording: freshness.recording })}
>
  {#snippet actions()}
    <span class="note">All repos, click a name to filter</span>
    <MetricTabs
      label="Measure repos by"
      {options}
      value={by}
      onchange={(v) => (by = v as RepoMetric)}
    />
  {/snippet}
  <BarList label="Repos" rows={bars} color={COLORS[by]} {columns} onpick={(key) => setRepos([key])} />
</Module>

<style>
  .note {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
