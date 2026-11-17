<script lang="ts">
  import { getGates } from "../lib/api";
  import EmptyState from "../lib/components/EmptyState.svelte";
  import GateTable from "../lib/components/GateTable.svelte";
  import Notice from "../lib/components/Notice.svelte";
  import { gateKey } from "../lib/gates";
  import { closeGatePanel, openGatePanel } from "../lib/panel";
  import { createQuery } from "../lib/query.svelte";
  import { emptyHint, emptyTitle } from "../lib/scope";
  import { filters, freshness } from "../lib/state.svelte";
  import GateDetail from "./GateDetail.svelte";

  interface Props {
    /** The gate whose detail panel is open, if any. */
    open: { repo: string | null; name: string } | null;
    repoLabel: string | null;
  }

  let { open, repoLabel }: Props = $props();

  const query = createQuery((signal) => getGates({ signal }));

  const openKey = $derived(open ? gateKey(open) : null);
</script>

<section class="page" aria-labelledby="gates-title">
  <h1 id="gates-title" class="page-title">Gates</h1>

  {#if query.error}
    <Notice tone="error">Could not load gates: {query.error.message}</Notice>
  {/if}

  {#if query.data}
    <GateTable
      label="Gates"
      rows={query.data}
      activeKey={openKey}
      onRowClick={(g) => openGatePanel(g)}
      busy={query.loading}
    >
      {#snippet empty()}
        <EmptyState
          title={emptyTitle("runs", { range: filters.range, repoLabel })}
          detail={emptyHint({ range: filters.range, repoLabel, recording: freshness.recording })}
        />
      {/snippet}
    </GateTable>
  {:else if query.loading}
    <p class="loading" aria-live="polite">Loading gates</p>
  {/if}
</section>

{#if open}
  <GateDetail
    repo={open.repo}
    name={open.name}
    onclose={() => closeGatePanel(openKey, { page: "gates" })}
  />
{/if}

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .loading {
    margin: 0;
    color: var(--text-muted);
  }
</style>
