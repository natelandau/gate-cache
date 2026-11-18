<!--
  @component
  The one tooltip surface in the app. Every tooltip renders through it, so its look (surface,
  shadow, corners, padding, type, left-aligned text) changes in one place. The caller decides
  where it shows and when, and sets any id or role on its own wrapper: an info tip places it
  under its label, and a chart hands it to LayerChart's `Tooltip.Root` with `variant="none"`.

  Give it either `text` for a plain explanation, or a `title` with `rows` of series values and
  an optional `hint` about what a click does.

  Props:
  - `text`: a plain explanation, such as what a column measures
  - `title`: the first line of a data tooltip, such as "Tue, Nov 4"
  - `rows`: one entry per series, each `{ color, label, value }` with `color` a CSS color
  - `hint`: optional muted line under a hairline
-->
<script lang="ts">
  interface Props {
    text?: string;
    title?: string;
    rows?: { color?: string; label: string; value: string }[];
    hint?: string;
  }

  let { text, title, rows = [], hint }: Props = $props();
</script>

<span class="tooltip" class:data={title !== undefined}>
  {#if text}<span class="text">{text}</span>{/if}
  {#if title}<span class="title">{title}</span>{/if}
  {#each rows as row, i (i)}
    <span class="row">
      <i class="bar" style:background={row.color ?? "transparent"}></i>
      <span class="label">{row.label}</span>
      <span class="value">{row.value}</span>
    </span>
  {/each}
  {#if hint}<span class="hint">{hint}</span>{/if}
</span>

<style>
  .tooltip {
    display: block;
    width: max-content;
    max-width: 280px;
    padding: var(--space-2) 10px;
    border-radius: var(--radius-popover);
    background: var(--surface);
    box-shadow: var(--shadow-popover);
    color: var(--text);
    font-size: var(--text-xs);
    font-weight: 400;
    line-height: 16px;
    letter-spacing: 0;
    text-align: left;
    white-space: normal;
  }

  /* A chart mounts its tooltip as it appears, so the tooltip fades itself in. */
  .data {
    min-width: 168px;
    animation: fade-in var(--dur-fast) var(--ease-in);
  }

  .text,
  .title,
  .hint {
    display: block;
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
