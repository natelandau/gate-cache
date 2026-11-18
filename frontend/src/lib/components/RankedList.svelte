<!--
  @component
  A numbered list of ranked items: rank, title with a muted subtitle below it, an optional
  inline bar, and the value at the right. A row with `onselect` is a button.

  Props:
  - `items`: the rows, best first; `tone: "danger"` marks a failure count; `share` (0 to 1)
    draws an inline bar in `barColor`
-->
<script lang="ts">
  import Meter from "./Meter.svelte";

  interface Item {
    key: string;
    title: string;
    subtitle: string;
    value: string;
    tone?: "danger";
    share?: number;
    barColor?: string;
    onselect?: () => void;
  }

  interface Props {
    items: Item[];
  }

  let { items }: Props = $props();
</script>

<ol class="ranked">
  {#each items as item, index (item.key)}
    <li>
      {#snippet row()}
        <span class="rank">{index + 1}</span>
        <span class="name">
          <span class="title" title={item.title}>{item.title}</span>
          <span class="subtitle" title={item.subtitle}>{item.subtitle}</span>
        </span>
        {#if item.share !== undefined}
          <Meter share={item.share} color={item.barColor ?? "var(--chart-runs)"} />
        {/if}
        <span class="value" class:danger={item.tone === "danger"}>{item.value}</span>
      {/snippet}
      {#if item.onselect}
        <button type="button" class="row" class:plain={item.share === undefined} onclick={item.onselect}>{@render row()}</button>
      {:else}
        <div class="row" class:plain={item.share === undefined}>{@render row()}</div>
      {/if}
    </li>
  {/each}
</ol>

<style>
  .ranked {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    border-bottom: 1px solid var(--border-row);
  }

  li:last-child {
    border-bottom: 0;
  }

  .row {
    display: grid;
    grid-template-columns: 20px minmax(0, 1fr) minmax(48px, 22%) minmax(64px, auto);
    gap: 12px;
    align-items: center;
    width: 100%;
    min-height: 46px;
    padding: var(--space-1) var(--space-1);
    border: 0;
    border-radius: var(--radius-chip);
    background: none;
    color: inherit;
    font: inherit;
    font-size: var(--text-sm);
    text-align: left;
    transition: background-color var(--dur-fast) var(--ease);
  }

  .row.plain {
    grid-template-columns: 20px minmax(0, 1fr) auto;
  }

  button.row {
    cursor: pointer;
  }

  button.row:hover {
    background: var(--surface-hover);
  }

  /* Inset so the ring stays inside the list instead of overlapping the next row. */
  button.row:focus-visible {
    outline-offset: -2px;
  }

  .rank {
    color: var(--text-faint);
    font-size: var(--text-xs);
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .name {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .title {
    overflow: hidden;
    font-size: var(--text-md);
    font-weight: 500;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .subtitle {
    overflow: hidden;
    color: var(--text-muted);
    font-size: var(--text-xs);
    text-overflow: ellipsis;
    white-space: nowrap;
  }


  .value {
    font-weight: 500;
    font-variant-numeric: tabular-nums;
    text-align: right;
    white-space: nowrap;
  }

  .danger {
    color: var(--danger);
  }
</style>
