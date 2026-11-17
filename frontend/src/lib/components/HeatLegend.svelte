<!--
  @component
  The "Less ... More" key for a heatmap: one swatch per ramp step of the active metric. It is
  hidden from screen readers, which read the heatmap's table instead.

  Props:
  - `metric`: the ramp to show
-->
<script lang="ts">
  import { heatColor, type HeatMetric } from "../heat";

  interface Props {
    metric: HeatMetric;
  }

  let { metric }: Props = $props();
</script>

<div class="legend" aria-hidden="true">
  <span>Less</span>
  {#each [0, 1, 2, 3, 4, 5] as step (step)}
    <i style:background={heatColor(metric, step)}></i>
  {/each}
  <span>More</span>
</div>

<style>
  .legend {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 3px;
    margin-top: var(--space-2);
    font-size: var(--text-xs);
    color: var(--text-faint);
  }

  .legend span:first-child {
    margin-right: 2px;
  }

  .legend span:last-child {
    margin-left: 2px;
  }

  i {
    width: 11px;
    height: 11px;
    border-radius: 2px;
  }
</style>
