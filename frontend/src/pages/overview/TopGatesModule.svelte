<!--
  @component
  Top gates: the gates that saved or spent the most time, ran most, failed most, or run slowest. A row opens
  the gate's detail panel.

  Props:
  - `repoLabel`: the repo selection's display name, or null for all repos
  - `span`: page-local days the overview is scoped to, if any
-->
<script lang="ts">
  import { getGates, spanScope } from "../../lib/api";
  import MetricTabs from "../../lib/components/MetricTabs.svelte";
  import Module from "../../lib/components/Module.svelte";
  import RankedList from "../../lib/components/RankedList.svelte";
  import { formatCount, formatDuration } from "../../lib/format";
  import { gateKey } from "../../lib/gates";
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

  let by: GateRank = $state("saved");

  const options: { value: GateRank; label: string }[] = [
    { value: "saved", label: "Time saved" },
    { value: "spent", label: "Time spent" },
    { value: "runs", label: "Runs" },
    { value: "fails", label: "Failures" },
    { value: "slow", label: "Slowest" },
  ];

  // What an empty tab lacks, for its empty state.
  const SUBJECT: Record<GateRank, string> = {
    saved: "time saved",
    spent: "time spent",
    runs: "runs",
    fails: "failures",
    slow: "passing runs",
  };

  // A zero value ranks nothing, so a tab lists only gates that have some of its measure.
  const ranked = $derived(
    rankGates((query.data ?? []).filter((row) => (rankValue(row, by) ?? 0) > 0), by),
  );

  const items = $derived(
    ranked.map((row) => ({
      key: gateKey(row),
      title: row.name,
      subtitle: [row.repo_name, gateRunText(row)].filter(Boolean).join(" \u00b7 "),
      value:
        by === "saved" || by === "spent" || by === "slow"
          ? formatDuration(rankValue(row, by))
          : formatCount(rankValue(row, by) ?? 0),
      tone: by === "fails" ? ("danger" as const) : ("accent" as const),
      onselect: () => openGatePanel(row),
    })),
  );

  const subject = $derived(query.data?.length === 0 ? "runs" : SUBJECT[by]);
</script>

<Module
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
  <a class="more-link" href={href({ page: "gates" })}>All gates <span aria-hidden="true">→</span></a>
</Module>
