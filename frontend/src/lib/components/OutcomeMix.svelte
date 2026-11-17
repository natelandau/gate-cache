<!--
  @component
  The share of each outcome as one stacked bar, with a legend that lists every outcome, its
  count, and its percent. The legend is the text equivalent, so only the bar is hidden from
  screen readers.

  Props:
  - `counts`: runs per outcome; pass a nonzero total
-->
<script lang="ts">
  import type { Outcome } from "../api";
  import { OUTCOMES } from "../events";
  import { formatCount } from "../format";
  import { outcomeShares } from "../rank";

  interface Props {
    counts: Record<Outcome, number>;
  }

  let { counts }: Props = $props();

  const COLORS: Record<Outcome, string> = {
    skip: "var(--chart-skip)",
    pass: "var(--chart-pass)",
    pass_unrecorded: "var(--chart-pass-unrecorded)",
    fail: "var(--chart-fail)",
    uncached: "var(--chart-uncached)",
  };

  const shares = $derived(outcomeShares(counts));
</script>

<figure class="mix">
  <div class="bar" aria-hidden="true">
    {#each shares as item (item.outcome)}
      {#if item.count > 0}
        <span
          class="segment"
          style:background={COLORS[item.outcome]}
          style:width="{item.share * 100}%"
          title="{OUTCOMES[item.outcome].label}: {formatCount(item.count)} ({item.percent})"
        ></span>
      {/if}
    {/each}
  </div>
  <ul class="legend">
    {#each shares as item (item.outcome)}
      <li>
        <i class="swatch" style:background={COLORS[item.outcome]}></i>
        <span>{OUTCOMES[item.outcome].label}</span>
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
