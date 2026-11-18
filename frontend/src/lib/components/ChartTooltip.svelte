<!--
  @component
  The body of every chart tooltip: a bold title such as the day, one row per series with its
  color bar and value, and an optional hint about what a click does. Render it inside a
  LayerChart `Tooltip.Root` with `variant="none"`.

  Props:
  - `title`: the first line, such as "Tue, Nov 4"
  - `rows`: one entry per series, each `{ color, label, value }` with `color` a CSS color
  - `hint`: optional muted line under a hairline
-->
<script lang="ts">
  interface Props {
    title: string;
    rows: { color?: string; label: string; value: string }[];
    hint?: string;
  }

  let { title, rows, hint }: Props = $props();
</script>

<div class="tip">
  <p class="title">{title}</p>
  {#each rows as row (row.label)}
    <p class="row">
      <i class="bar" style:background={row.color ?? "transparent"}></i>
      <span class="label">{row.label}</span>
      <span class="value">{row.value}</span>
    </p>
  {/each}
  {#if hint}<p class="hint">{hint}</p>{/if}
</div>

<style>
  .tip {
    min-width: 168px;
    max-width: 280px;
    padding: var(--space-2) 10px;
    border-radius: var(--radius-popover);
    background: var(--surface);
    box-shadow: var(--shadow-popover);
    color: var(--text);
    font-size: var(--text-xs);
    line-height: 16px;
    animation: fade-in var(--dur-fast) var(--ease-in);
  }

  p {
    margin: 0;
  }

  .title {
    margin-bottom: var(--space-1);
    font-weight: 600;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 7px;
    margin-top: 3px;
  }

  .bar {
    flex: none;
    width: 3px;
    height: 12px;
    border-radius: 2px;
  }

  .label {
    min-width: 0;
    overflow: hidden;
    color: var(--text-muted);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .value {
    margin-left: auto;
    padding-left: var(--space-3);
    font-weight: 500;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .hint {
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid var(--border);
    color: var(--text-muted);
  }
</style>
