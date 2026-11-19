<!--
  @component
  The Triage rows: one card per gate and reason, in the order given, each with the gate, a
  reason badge, what to check, and the evidence that fits the reason.

  Props:
  - `items`: the rows to show, already filtered
  - `busy`: true while new rows load, which dims the list
-->
<script lang="ts">
  import type { TriageItem } from "../../lib/api";
  import Badge from "../../lib/components/Badge.svelte";
  import GateName from "../../lib/components/GateName.svelte";
  import { formatRelative, formatTimestamp } from "../../lib/format";
  import { href } from "../../lib/router.svelte";
  import { clock } from "../../lib/state.svelte";
  import { TRIAGE } from "../../lib/terms";
  import { triageKey } from "../../lib/triage";
  import { evidenceOf, REASON_VIEWS } from "./reasons";

  interface Props {
    items: TriageItem[];
    busy?: boolean;
  }

  let { items, busy = false }: Props = $props();
</script>

<ul class="items bare-list" aria-busy={busy} class:busy>
  {#each items as item (triageKey(item))}
    {@const Evidence = evidenceOf(item)}
    {@const words = TRIAGE.reasons[item.reason]}
    <li class="outlined" data-reason={item.reason}>
      <header class="head">
        <h2 class="name">
          <a href={href({ page: "gate", repo: item.repo, name: item.name })}><GateName name={item.name} /></a>
        </h2>
        <span class="muted" title={item.repo ?? undefined}>{item.repo_name}</span>
        <Badge tone={REASON_VIEWS[item.reason].tone}>{words.badge}</Badge>
        <span class="meta" title={formatTimestamp(item.last_seen)}>
          {formatRelative(item.last_seen, clock.now)}
        </span>
      </header>
      <p class="line">{words.line}</p>
      <Evidence {item} />
    </li>
  {/each}
</ul>

<style>
  .items {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .busy {
    opacity: 0.55;
  }

  .head {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-3);
    padding: var(--space-2) var(--space-3);
    background: var(--surface-sunken);
    border-radius: var(--radius-control) var(--radius-control) 0 0;
  }

  .name {
    font-size: var(--text-md);
  }

  .name a {
    color: var(--text);
    text-decoration-color: var(--border-strong);
    text-underline-offset: 3px;
  }

  .name a:hover {
    text-decoration-color: currentColor;
  }

  .meta {
    margin-left: auto;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  .line {
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-top: 1px solid var(--border);
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  .muted {
    color: var(--text-muted);
  }
</style>
