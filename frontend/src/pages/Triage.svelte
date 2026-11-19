<script lang="ts">
  import { getTriage, type TriageReason } from "../lib/api";
  import EmptyState from "../lib/components/EmptyState.svelte";
  import Notice from "../lib/components/Notice.svelte";
  import PageHeader from "../lib/components/PageHeader.svelte";
  import Select from "../lib/components/Select.svelte";
  import { createQuery } from "../lib/query.svelte";
  import { navigate } from "../lib/router.svelte";
  import { emptyHint, emptyTitle, scopeSubtitle } from "../lib/scope";
  import { filters, freshness } from "../lib/state.svelte";
  import { TRIAGE } from "../lib/terms";
  import { isTriageReason, TRIAGE_REASONS } from "../lib/triage";
  import { TESTS_CUTOFF_NOTE } from "./GateDetail.svelte";
  import TriageList from "./triage/TriageList.svelte";

  interface Props {
    repoLabel: string | null;
    /** The page-local reason filter from the hash route. */
    reason?: TriageReason;
    /** Rows for every reason under the global filters, or null while unknown. */
    total: number | null;
  }

  let { repoLabel, reason, total }: Props = $props();

  const query = createQuery(
    (signal) => getTriage({ signal, reason }),
    () => reason,
  );
  const subtitle = $derived(scopeSubtitle(repoLabel, filters.range));
  const rows = $derived(query.data?.items ?? []);
  const showCutoff = $derived(
    query.data?.tests_cutoff != null &&
      rows.some((r) => r.reason === "flaky" && (r.evidence.tests.length || r.evidence.retried.length)),
  );
  const subject = $derived(reason ? TRIAGE.reasons[reason].subject : TRIAGE.subject);

  const reasonOptions = [
    { value: "", label: TRIAGE.allReasons },
    ...TRIAGE_REASONS.map((value) => ({ value, label: TRIAGE.reasons[value].badge })),
  ];

  // Filter changes replace the history entry, as on Activity.
  function showReason(value: string): void {
    navigate(isTriageReason(value) ? { page: "triage", reason: value } : { page: "triage" }, { replace: true });
  }
</script>

<section class="page" aria-labelledby="triage-title">
  <div>
    <PageHeader title={TRIAGE.title} headingId="triage-title" {subtitle} />
    <p class="lede">{TRIAGE.lede}</p>
  </div>

  <div class="filters">
    <Select label={TRIAGE.filter} value={reason ?? ""} options={reasonOptions} onchange={showReason} />
  </div>

  {#if query.error}
    <Notice tone="error">Could not load {TRIAGE.subject}: {query.error.message}</Notice>
  {/if}

  {#if query.data}
    {#if rows.length === 0}
      <div class="outlined">
        <EmptyState
          title={emptyTitle(subject, { range: filters.range, repoLabel })}
          detail={reason && total
            ? TRIAGE.otherReasons
            : emptyHint({ range: filters.range, repoLabel, recording: freshness.recording })}
        >
          <p class="definition">{TRIAGE.definition}</p>
        </EmptyState>
      </div>
    {:else}
      <TriageList items={rows} busy={query.loading} />
      {#if showCutoff}
        <p class="muted note">{TESTS_CUTOFF_NOTE}</p>
      {/if}
    {/if}
  {:else if query.loading}
    <p class="muted" aria-live="polite">Loading {TRIAGE.subject}</p>
  {/if}
</section>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .lede {
    margin: var(--space-2) 0 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  .filters {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
  }

  .definition {
    margin: 0;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  .muted {
    color: var(--text-muted);
  }

  .note {
    margin: 0;
    font-size: var(--text-xs);
  }
</style>
