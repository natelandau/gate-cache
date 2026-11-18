<!--
  @component
  Top gates: the gates that saved or spent the most time, ran most, failed most, or run slowest. A row opens
  the gate's detail panel.

  Props:
  - `repoLabel`: the repo selection's display name, or null for all repos
  - `span`: page-local days the overview is scoped to, if any
-->
<script lang="ts">
  import { TERMS } from "../../lib/terms";
  import { getGates, spanScope } from "../../lib/api";
  import MetricTabs from "../../lib/components/MetricTabs.svelte";
  import Module from "../../lib/components/Module.svelte";
  import RankedList from "../../lib/components/RankedList.svelte";
  import { formatCount, formatDuration } from "../../lib/format";
  import { gateKey } from "../../lib/gates";
  import { METRIC_COLORS } from "../../lib/heat";
  import { openGatePanel } from "../../lib/panel";
  import { createQuery } from "../../lib/query.svelte";
  import { gateRunText, rankGates, rankValue, type GateRank } from "../../lib/rank";
  import { href } from "../../lib/router.svelte";
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
    (signal) => getGates({ signal, scope: spanScope(span) }),
    () => span,
  );

  let by: GateRank = $state("spent");

  const options: { value: GateRank; label: string }[] = [
    { value: "spent", label: TERMS.ran.column },
    { value: "saved", label: TERMS.saved.column },
    { value: "runs", label: TERMS.calls.column },
    { value: "fails", label: "Failures" },
    { value: "slow", label: "Slowest" },
  ];

  // What an empty tab lacks, for its empty state.
  const SUBJECT: Record<GateRank, string> = {
    saved: TERMS.saved.noun,
    spent: TERMS.ran.noun,
    runs: TERMS.calls.many,
    fails: "failures",
    slow: "passing runs",
  };

  // A zero value ranks nothing, so a tab lists only gates that have some of its measure.
  const ranked = $derived(
    rankGates((query.data ?? []).filter((row) => (rankValue(row, by) ?? 0) > 0), by),
  );

  const BAR_COLORS: Record<GateRank, string> = {
    saved: METRIC_COLORS.saved,
    spent: METRIC_COLORS.runs,
    runs: METRIC_COLORS.runs,
    fails: METRIC_COLORS.fail,
    slow: METRIC_COLORS.runs,
  };
  const top = $derived(Math.max(0, ...ranked.map((row) => rankValue(row, by) ?? 0)));

  const items = $derived(
    ranked.map((row) => ({
      share: top > 0 ? (rankValue(row, by) ?? 0) / top : 0,
      barColor: BAR_COLORS[by],
      key: gateKey(row),
      title: row.name,
      subtitle: [row.repo_name, gateRunText(row)].filter(Boolean).join(" \u00b7 "),
      value:
        by === "saved" || by === "spent" || by === "slow"
          ? formatDuration(rankValue(row, by))
          : formatCount(rankValue(row, by) ?? 0),
      tone: by === "fails" ? ("danger" as const) : undefined,
      onselect: () => openGatePanel(row),
    })),
  );

  const subject = $derived(query.data?.length === 0 ? "runs" : SUBJECT[by]);
</script>

<Module
  more={{ href: href({ page: "gates" }), label: "All gates" }}
  title="Top gates"
  titleId="top-gates-title"
  loading={query.loading && !query.data}
  error={query.error}
  empty={!query.data || items.length === 0}
  emptyTitle={emptyTitle(subject, { range: filters.range, span, repoLabel })}
  emptyDetail={emptyHint({ range: filters.range, span, repoLabel, recording: freshness.recording })}
>
  {#snippet actions()}
    <MetricTabs
      label="Rank gates by"
      {options}
      value={by}
      onchange={(v) => (by = v as GateRank)}
    />
  {/snippet}
  <RankedList {items} />
</Module>
