<!--
  @component
  A numbered list of ranked items: rank, title with a muted subtitle below it, and the value
  at the right in monospace. A row with `onselect` is a button.

  Props:
  - `items`: the rows, best first; `tone` colors the value ("accent" by default, "danger"
    for failures)
-->
<script lang="ts">
  interface Item {
    key: string;
    title: string;
    subtitle: string;
    value: string;
    tone?: "accent" | "danger";
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
          <span class="title">{item.title}</span>
          <span class="subtitle">{item.subtitle}</span>
        </span>
        <span class="value {item.tone ?? 'accent'} mono">{item.value}</span>
      {/snippet}
      {#if item.onselect}
        <button type="button" class="row" onclick={item.onselect}>{@render row()}</button>
      {:else}
        <div class="row">{@render row()}</div>
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
    border-bottom: 1px solid var(--border);
  }

  li:last-child {
    border-bottom: 0;
  }

  .row {
    display: grid;
    grid-template-columns: 20px minmax(0, 1fr) auto;
    gap: 10px;
    align-items: center;
    width: 100%;
    padding: var(--space-1) var(--space-2);
    border: 0;
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
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
    font-size: var(--text-sm);
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
    font-variant-numeric: tabular-nums;
  }

  .accent {
    color: var(--accent);
  }

  .danger {
    color: var(--danger);
  }
</style>
