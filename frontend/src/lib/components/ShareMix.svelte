<!--
  @component
  The share of each part of a whole as one stacked bar, with a legend that lists every part,
  its count, and its percent. The legend is the text equivalent, so only the bar is hidden from
  screen readers.

  Props:
  - `parts`: the parts in display order, each `{ key, label, count, color, title? }`; pass a
    nonzero total
-->
<script lang="ts">
  import { formatCount } from "../format";
  import { type MixPart, partShares } from "../rank";

  interface Props {
    parts: MixPart[];
  }

  let { parts }: Props = $props();

  const shares = $derived(partShares(parts, (part) => part.count));
</script>

<figure class="mix">
  <div class="bar" aria-hidden="true">
    {#each shares as item (item.part.key)}
      {#if item.count > 0}
        <span
          class="segment"
          style:background={item.part.color}
          style:width="{item.share * 100}%"
          title="{item.part.label}: {formatCount(item.count)} ({item.percent})"
        ></span>
      {/if}
    {/each}
  </div>
  <ul class="legend">
    {#each shares as item (item.part.key)}
      <li title={item.part.title}>
        <i class="swatch" style:background={item.part.color}></i>
        <span>{item.part.label}</span>
        <span class="mono num">{formatCount(item.count)}</span>
        <span class="mono num percent">{item.percent}</span>
      </li>
    {/each}
  </ul>
</figure>

<style>
  .mix {
    margin: 0;
  }

  .bar {
    display: flex;
    height: 18px;
    overflow: hidden;
    border-radius: 3px;
    background: var(--surface-sunken);
  }

  .segment {
    height: 100%;
  }

  .legend {
    display: grid;
    grid-template-columns: 12px minmax(0, 1fr) auto auto;
    gap: var(--space-1) var(--space-2);
    align-items: center;
    margin: var(--space-3) 0 0;
    padding: 0;
    font-size: var(--text-sm);
    list-style: none;
  }

  li {
    display: grid;
    grid-column: 1 / -1;
    grid-template-columns: subgrid;
    align-items: center;
  }

  .swatch {
    width: 10px;
    height: 10px;
    border-radius: 2px;
  }

  .percent {
    color: var(--text-muted);
  }
</style>
