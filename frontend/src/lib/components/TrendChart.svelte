<!--
  @component
  How long a gate's passing runs took over time, one point per pass.

  Props:
  - `trend`: pass durations, oldest first, as the gate detail returns them
-->
<script lang="ts">
  import type { ChartState } from "layerchart";
  import { LineChart, Tooltip } from "layerchart/svg";
  import type { GateDetail } from "../api";
  import { durationTicks, formatAxisDuration, formatDuration, formatTimestamp } from "../format";
  import { trendStats } from "../gates";
  import ChartTooltip from "./ChartTooltip.svelte";

  interface Props {
    trend: GateDetail["trend"];
  }

  let { trend }: Props = $props();

  interface Point {
    date: Date;
    duration: number;
  }

  const points = $derived(trend.map((p): Point => ({ date: new Date(p.ts * 1000), duration: p.duration })));
  const stats = $derived(trendStats(trend));
  const ticks = $derived(durationTicks(Math.max(0, ...trend.map((p) => p.duration))));
  const top = $derived(Math.max(1, ticks.at(-1) ?? 0));

  // Within two days the times of day matter more than the dates.
  const span = $derived(trend.length ? trend.at(-1)!.ts - trend[0]!.ts : 0);
  const tickFormat = $derived(
    new Intl.DateTimeFormat(
      undefined,
      span < 2 * 86400 ? { hour: "numeric", minute: "2-digit" } : { month: "short", day: "numeric" },
    ),
  );

  const color = "var(--chart-runs)";
</script>

{#snippet pointTooltip(context: ChartState<Point>)}
  <Tooltip.Root {context} variant="none" motion="none">
    {#snippet children({ data }: { data: Point })}
      <ChartTooltip
        title={formatTimestamp(data.date.getTime() / 1000)}
        rows={[{ color, label: "Ran for", value: formatDuration(data.duration) }]}
      />
    {/snippet}
  </Tooltip.Root>
{/snippet}

<figure class="trend">
  <figcaption class="caption">
    {stats.count}
    {stats.count === 1 ? "pass" : "passes"} · median {formatDuration(stats.median)} · latest
    {formatDuration(stats.latest)}
  </figcaption>
  <div class="plot" aria-hidden="true">
    <LineChart
      data={points}
      x="date"
      y="duration"
      yDomain={[0, top]}
      series={[{ key: "duration", label: "Ran", value: "duration", color }]}
      padding={{ top: 8, right: 8, bottom: 20, left: 44 }}
      rule={false}
      points={{ r: 3 }}
      grid={{ x: false, y: true, yTicks: ticks }}
      props={{
        // Few ticks: the panel is narrow, and month-boundary labels otherwise collide.
        xAxis: { ticks: 4, tickLength: 3, format: (d: Date) => tickFormat.format(d) },
        yAxis: { ticks, tickLength: 0, format: formatAxisDuration },
        spline: { strokeWidth: 1.5 },
      }}
    >
      {#snippet tooltip({ context })}{@render pointTooltip(context)}{/snippet}
    </LineChart>
  </div>
</figure>

<style>
  .trend {
    margin: 0;
  }

  .caption {
    font-size: var(--text-xs);
    color: var(--text-muted);
    margin-bottom: var(--space-1);
  }

  .plot {
    height: 140px;
  }

  .trend :global(.lc-axis-tick-label),
  .trend :global(text) {
    font-size: var(--text-xs);
    fill: var(--text-muted);
  }

  .trend :global(.lc-grid-line),
  .trend :global(.lc-grid line) {
    stroke: var(--chart-grid);
  }
</style>
