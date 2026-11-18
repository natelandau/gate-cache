<!--
  @component
  Recent failures: the latest failed runs with when, gate, repo, exit code, and run time. A
  row opens the gate's detail panel.

  Props:
  - `repoLabel`: the repo selection's display name, or null for all repos
  - `span`: page-local days the overview is scoped to, if any
-->
<script lang="ts">
  import { getActivity, spanScope, type EventRow } from "../../lib/api";
  import DataTable, { type Column } from "../../lib/components/DataTable.svelte";
  import Module from "../../lib/components/Module.svelte";
  import { eventKeys } from "../../lib/events";
  import { formatDuration, formatRelative, formatTimestamp } from "../../lib/format";
  import { openGatePanel } from "../../lib/panel";
  import { createQuery } from "../../lib/query.svelte";
  import { activityHref } from "../../lib/router.svelte";
  import { emptyHint, emptyTitle } from "../../lib/scope";
  import type { DaySpan } from "../../lib/selection";
  import { clock, filters, freshness } from "../../lib/state.svelte";

  interface Props {
    repoLabel: string | null;
    /** Page-local days the overview is scoped to. */
    span?: DaySpan;
  }

  let { repoLabel, span }: Props = $props();

  const LIMIT = 5;

  const query = createQuery(
    (signal) =>
      getActivity({ outcome: "fail", limit: LIMIT }, { signal, scope: spanScope(span) }),
    () => span,
  );

  type Failure = EventRow & { key: string };
  const rows = $derived.by<Failure[]>(() => {
    const events = query.data?.events ?? [];
    const keys = eventKeys(events);
    return events.map((event, index) => ({ ...event, key: keys[index]! }));
  });

  const columns: Column<Failure>[] = [
    {
      key: "ts",
      label: "When",
      sortable: false,
      text: (e) => formatRelative(e.ts, clock.now),
      title: (e) => formatTimestamp(e.ts),
    },
    { key: "name", label: "Gate", sortable: false },
    { key: "repo_name", label: "Repo", sortable: false, title: (e) => e.repo ?? undefined },
    {
      key: "exit_code",
      label: "Exit code",
      align: "right",
      sortable: false,
      text: (e) => (e.exit_code === null ? "n/a" : String(e.exit_code)),
    },
    {
      key: "duration",
      label: "Ran for",
      align: "right",
      sortable: false,
      text: (e) => formatDuration(e.duration),
    },
  ];
</script>

<Module
  more={{ href: activityHref({ outcome: "fail" }, span), label: "All failures in Activity" }}
  title="Recent failures"
  titleId="failures-title"
  noun="failures"
  loading={query.loading && !query.data}
  error={query.error}
  empty={!query.data || query.data.events.length === 0}
  emptyTitle={emptyTitle("failures", { range: filters.range, span, repoLabel })}
  emptyDetail={emptyHint({ range: filters.range, span, repoLabel, recording: freshness.recording })}
>
  <DataTable
    label="Recent failures"
    bare
    {rows}
    rowKey={(e) => e.key}
    {columns}
    onRowClick={(e) => openGatePanel(e)}
    rowLabel={(e) => `Open ${e.name}`}
    busy={query.loading}
  />
</Module>
