<!--
  @component
  How a gate's passing run times spread across equal-width bins, with the median and p90 marked
  as labeled vertical rules. The caption is the text equivalent, so only the plot is hidden from
  screen readers.

  Props:
  - `histogram`: the bins, median, and p90 as the gate detail returns them
-->
<script lang="ts">
  import type { GateDetail } from "../api";
  import { MIN_BAR_PX } from "../bars";
  import { formatCount, formatDuration } from "../format";
  import { histogramBars } from "../gates";

  interface Props {
    histogram: NonNullable<GateDetail["histogram"]>;
  }

  let { histogram }: Props = $props();

  const bars = $derived(histogramBars(histogram));
  const peak = $derived(Math.max(1, ...bars.map((bar) => bar.count)));
  const start = $derived(histogram.edges[0] ?? 0);
  const span = $derived(Math.max(1e-9, (histogram.edges.at(-1) ?? 0) - start));

  const rules = $derived(
    [
      { key: "median", label: "median", value: histogram.median },
      { key: "p90", label: "p90", value: histogram.p90 },
    ].map((rule) => {
      const percent = Math.min(100, Math.max(0, ((rule.value - start) / span) * 100));
      return { ...rule, percent, flip: percent > 60 };
    }),
  );
</script>

<figure class="histogram">
  <figcaption class="caption">
    median {formatDuration(histogram.median)} · p90 {formatDuration(histogram.p90)}
  </figcaption>
  <div class="plot" aria-hidden="true">
    <div class="bars">
      {#each bars as bar (bar.from)}
        <div
          class="bar"
          style:height="{(bar.count / peak) * 100}%"
          style:min-height="{bar.count ? MIN_BAR_PX : 0}px"
          title="{bar.label}: {formatCount(bar.count)} {bar.count === 1 ? 'run' : 'runs'}"
        ></div>
      {/each}
      {#each rules as rule, i (rule.key)}
        <div class="rule" style:left="{rule.percent}%">
          <span class="rule-label" class:flip={rule.flip} style:top="{i * 14}px">
            {rule.label}
            {formatDuration(rule.value)}
          </span>
        </div>
      {/each}
    </div>
    <div class="axis">
      <span>{formatDuration(histogram.edges[0] ?? 0)}</span>
      <span>{formatDuration(histogram.edges.at(-1) ?? 0)}</span>
    </div>
  </div>
</figure>

<style>
  .histogram {
    margin: 0;
  }

  .caption {
    font-size: var(--text-xs);
    color: var(--text-muted);
    margin-bottom: var(--space-1);
  }

  .bars {
    position: relative;
    display: flex;
    align-items: flex-end;
    gap: 2px;
    height: 120px;
    border-bottom: 1px solid var(--chart-grid);
  }

  .bar {
    flex: 1;
    background: var(--chart-runs);
    border-radius: 2px 2px 0 0;
  }

  .rule {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 0;
    border-left: 1.5px dashed var(--text);
    pointer-events: none;
  }

  .rule-label {
    position: absolute;
    left: 4px;
    padding: 0 2px;
    font-size: var(--text-xs);
    white-space: nowrap;
    color: var(--text);
    background: var(--bg);
  }

  .rule-label.flip {
    left: auto;
    right: 4px;
  }

  .axis {
    display: flex;
    justify-content: space-between;
    margin-top: 2px;
    font-size: var(--text-xs);
    color: var(--text-muted);
  }
</style>
