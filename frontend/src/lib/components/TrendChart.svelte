<!--
  @component
  How long a gate's passing runs took, in run order. Each pass is a dot, a rolling median shows
  the trend, and a long idle stretch between runs shows as a labeled gap break instead of a line
  across days with no runs. Too many passes collapse into buckets with a min-to-max whisker, and
  too few show as a list instead of a plot.

  Props:
  - `trend`: pass durations, oldest first, as the gate detail returns them
-->
<script lang="ts">
  import type { ChartState } from "layerchart";
  import { Axis, Chart, Grid, Layer, Spline, Tooltip } from "layerchart/svg";
  import type { GateDetail } from "../api";
  import {
    DAY,
    durationTicks,
    formatAxisDuration,
    formatDuration,
    formatGap,
    formatIdle,
    formatPercent,
    formatTimestamp,
    plural,
  } from "../format";
  import { trendStats } from "../gates";
  import {
    dotStyle,
    gapLabels,
    labelSlots,
    MIN_PLOTTED,
    trendChange,
    trendLayout,
    type TrendMark,
  } from "../trend";
  import TooltipSurface from "./TooltipSurface.svelte";

  interface Props {
    trend: GateDetail["trend"];
  }

  let { trend }: Props = $props();

  const padding = { top: 18, right: 8, bottom: 20, left: 44 };
  const color = "var(--chart-runs)";

  const stats = $derived(trendStats(trend));
  const change = $derived(trendChange(trend));
  const layout = $derived(trendLayout(trend));
  const dot = $derived(dotStyle(layout.marks.length));
  const ticks = $derived(durationTicks(Math.max(0, ...layout.marks.map((m) => m.max))));
  const top = $derived(Math.max(1, ticks.at(-1) ?? 0));
  // One line for every stretch: a point with no value between stretches breaks it at each gap.
  const rollingPoints = $derived(
    layout.segments.flatMap((segment, i) => (i ? [{ slot: segment[0]!.slot - 1, rolling: null }, ...segment] : segment)),
  );
  const bySlot = $derived(new Map(layout.marks.map((m) => [m.slot, m])));

  let width = $state(0);
  const plotWidth = $derived(width - padding.left - padding.right);
  const labels = $derived(labelSlots(layout, plotWidth, slotLabel));
  const labeledGaps = $derived(new Set(gapLabels(layout, plotWidth)));

  // Within two days the times of day matter more than the dates.
  const span = $derived(trend.length ? trend.at(-1)!.ts - trend[0]!.ts : 0);
  const tickFormat = $derived(
    new Intl.DateTimeFormat(
      undefined,
      span < 2 * DAY ? { hour: "numeric", minute: "2-digit" } : { month: "short", day: "numeric" },
    ),
  );
  const shortTime = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

  function slotLabel(slot: number): string {
    const mark = bySlot.get(slot);
    return mark ? tickFormat.format(new Date(mark.ts * 1000)) : "";
  }

  const idleAt = $derived(new Map(layout.gaps.map((g) => [g.to, g.seconds])));

  function versusMedian(duration: number): string {
    if (!stats.median) return "n/a";
    const ratio = (duration - stats.median) / stats.median;
    const pct = formatPercent(Math.abs(ratio));
    if (pct === "0%") return "same as median";
    return `${ratio > 0 ? "+" : "\u2212"}${pct} vs median`;
  }

  function tooltipRows(mark: TrendMark): { color?: string; label: string; value: string }[] {
    const rows = mark.count > 1
      ? [
          { color, label: "Median", value: formatDuration(mark.duration) },
          { label: "Range", value: `${formatDuration(mark.min)} to ${formatDuration(mark.max)}` },
          { label: "Passes", value: String(mark.count) },
        ]
      : [{ color, label: "Ran for", value: formatDuration(mark.duration) }];
    rows.push({ label: "Compared", value: versusMedian(mark.duration) });
    const idle = idleAt.get(mark.slot);
    if (idle !== undefined) rows.push({ label: "Idle before", value: formatIdle(idle) });
    return rows;
  }

  function tooltipTitle(mark: TrendMark): string {
    if (mark.count === 1) return formatTimestamp(mark.ts);
    return `${shortTime.format(new Date(mark.ts * 1000))} to ${shortTime.format(new Date(mark.endTs * 1000))}`;
  }

  // A shift under 5% is noise between two medians, so it reads as no change.
  const trendText = $derived.by(() => {
    if (change === null) return null;
    const window = plural(change.window, "pass", "passes");
    if (Math.abs(change.change) < 0.05) return `last ${window} about the same as the first`;
    const pct = formatPercent(Math.abs(change.change));
    return `last ${window} ${pct} ${change.change > 0 ? "slower" : "faster"} than the first`;
  });
</script>

{#snippet markTooltip(context: ChartState<TrendMark>)}
  <Tooltip.Root {context} variant="none" motion="none">
    {#snippet children({ data }: { data: TrendMark })}
      <TooltipSurface title={tooltipTitle(data)} rows={tooltipRows(data)} />
    {/snippet}
  </Tooltip.Root>
{/snippet}

<figure class="trend">
  <figcaption class="caption">
    {plural(stats.count, "pass", "passes")} · median {formatDuration(stats.median)} · latest
    {formatDuration(stats.latest)}{#if trendText}{" · "}{trendText}{/if}
  </figcaption>
  {#if trend.length < MIN_PLOTTED}
    <ol class="passes">
      {#each [...trend].reverse() as pass (pass.ts)}
        <li>
          <span class="when">{formatTimestamp(pass.ts)}</span>
          <span class="took">{formatDuration(pass.duration)}</span>
        </li>
      {/each}
    </ol>
  {:else}
    <div class="plot" aria-hidden="true" bind:clientWidth={width}>
      <Chart
        data={layout.marks}
        x="slot"
        y="duration"
        xDomain={[-0.5, layout.slots - 0.5]}
        yDomain={[0, top]}
        {padding}
        tooltipContext={{ mode: "bisect-x" }}
      >
        {#snippet children({ context })}
          <Layer>
            {#each layout.gaps as gap (gap.from)}
              {@const x0 = context.xScale(gap.from + 0.5)}
              {@const x1 = context.xScale(gap.to - 0.5)}
              <rect class="gap" x={x0} y={-padding.top} width={Math.max(1, x1 - x0)} height={context.height + padding.top} />
              {#if labeledGaps.has(gap)}
                <text class="gap-label" x={(x0 + x1) / 2} y={-6} text-anchor="middle">{formatGap(gap.seconds)}</text>
              {/if}
            {/each}
            <Grid y yTicks={ticks} />
            <!-- The zero baseline needs no label, and one would collide with the first date. -->
            <Axis placement="left" ticks={ticks} tickLength={0} format={(v: number) => (v ? formatAxisDuration(v) : "")} />
            <Axis placement="bottom" ticks={labels} tickLength={3} format={slotLabel} />
            {#if stats.median !== null}
              {@const y = context.yScale(stats.median)}
              <line class="median" x1={0} x2={context.width} y1={y} y2={y} />
            {/if}
            {#if layout.bucketed}
              {#each layout.marks as mark (mark.slot)}
                {@const x = context.xScale(mark.slot)}
                <line class="whisker" x1={x} x2={x} y1={context.yScale(mark.min)} y2={context.yScale(mark.max)} />
              {/each}
            {/if}
            {#each layout.marks as mark (mark.slot)}
              <circle
                cx={context.xScale(mark.slot)}
                cy={context.yScale(mark.duration)}
                r={dot.r}
                fill={color}
                fill-opacity={dot.opacity}
              />
            {/each}
            <Spline
              data={rollingPoints}
              x="slot"
              y="rolling"
              defined={(m: Pick<TrendMark, "rolling">) => m.rolling !== null}
              class="rolling"
              stroke={color}
            />
            {#if context.tooltip.data}
              {@const hovered = context.tooltip.data as TrendMark}
              <circle
                class="hover"
                cx={context.xScale(hovered.slot)}
                cy={context.yScale(hovered.duration)}
                r={dot.r + 2}
                stroke={color}
              />
            {/if}
          </Layer>
          {@render markTooltip(context)}
        {/snippet}
      </Chart>
    </div>
  {/if}
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
    height: 150px;
  }

  .passes {
    list-style: none;
    margin: 0;
    padding: 0;
    font-size: var(--text-sm);
    font-variant-numeric: tabular-nums;
  }

  .passes li {
    display: flex;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-1) 0;
    border-bottom: 1px solid var(--border-row);
  }

  .passes li:last-child {
    border-bottom: 0;
  }

  .when {
    color: var(--text-muted);
  }

  .gap {
    fill: var(--surface-sunken);
  }

  .gap-label {
    fill: var(--text-faint);
    font-size: var(--text-xs);
  }

  .median {
    stroke: var(--border-strong);
    stroke-dasharray: 3 3;
  }

  .whisker {
    stroke: var(--chart-runs);
    stroke-opacity: 0.35;
  }

  .hover {
    fill: none;
    stroke-width: 1.5;
  }

  .plot :global(.rolling) {
    fill: none;
    stroke-width: 1.75;
    stroke-linejoin: round;
    stroke-linecap: round;
  }
</style>
