<!--
  @component
  When gates run: a 7 by 24 grid with weekdays (Sunday first) as rows and local hours as
  columns. Cells are colored on the metric's ramp, scaled to the busiest hour. Each cell's
  tooltip names the weekday, hour, and value, and a hidden table lists the same data.

  Props:
  - `cells`: the hourly buckets; a missing weekday and hour counts as zero
  - `metric`: which value to show and which ramp to use
-->
<script lang="ts">
  import type { HourCell } from "../api";
  import {
    formatHeatAmount,
    formatHeatValue,
    HEAT_LABELS,
    heatColor,
    heatStep,
    heatValue,
    hourLabel,
    METRIC_COLORS,
    weekdayName,
    type HeatMetric,
  } from "../heat";
  import { hourTotals, peakCell, weekdayTotals } from "../hourly";
  import HeatLegend from "./HeatLegend.svelte";

  interface Props {
    cells: HourCell[];
    metric: HeatMetric;
  }

  let { cells, metric }: Props = $props();

  const HOURS = Array.from({ length: 24 }, (_, hour) => hour);
  const WEEKDAYS = Array.from({ length: 7 }, (_, weekday) => ({
    short: weekdayName(weekday, "short"),
    long: weekdayName(weekday, "long"),
  }));

  const rows = $derived.by(() => {
    const byKey = new Map(cells.map((cell) => [`${cell.weekday}-${cell.hour}`, cell]));
    return WEEKDAYS.map((weekday, row) => ({
      ...weekday,
      values: HOURS.map((hour) => {
        const cell = byKey.get(`${row}-${hour}`);
        return cell ? heatValue(cell, metric) : 0;
      }),
    }));
  });

  const max = $derived(Math.max(0, ...rows.flatMap((row) => row.values)));

  const byHour = $derived(hourTotals(cells, metric));
  const byWeekday = $derived(weekdayTotals(cells, metric));
  const hourMax = $derived(Math.max(0, ...byHour));
  const weekdayMax = $derived(Math.max(0, ...byWeekday));
  const peak = $derived(peakCell(cells, metric));
</script>

<figure class="hours">
  <div class="grid" aria-hidden="true">
    <span aria-hidden="true"></span>
    {#each byHour as total, hour (hour)}
      <span class="hour-total" aria-hidden="true" title="{hourLabel(hour)}: {formatHeatValue(metric, total)}"
        ><i style:height="{hourMax ? (total / hourMax) * 100 : 0}%" style:background={METRIC_COLORS[metric]}></i></span
      >
    {/each}
    <span aria-hidden="true"></span>
    <span aria-hidden="true"></span>
    {#each HOURS as hour (hour)}<span class="hour" aria-hidden="true">{hour % 3 === 0 ? hour : ""}</span>{/each}
    <span aria-hidden="true"></span>
    {#each rows as row, weekday (row.long)}
      <span class="weekday" aria-hidden="true">{row.short}</span>
      {#each row.values as value, hour (hour)}
        {@const text = `${HEAT_LABELS[metric]}: ${formatHeatValue(metric, value)}`}
        {@const title = `${row.short} ${hourLabel(hour)}\n${text}`}
        <span class="cell" style:background={heatColor(metric, heatStep(value, max))} {title}></span>
      {/each}
      <span class="day-total" aria-hidden="true"
        ><i style:width="{weekdayMax ? (byWeekday[weekday]! / weekdayMax) * 28 : 0}px" style:background={METRIC_COLORS[metric]}
        ></i><span class="day-value">{formatHeatValue(metric, byWeekday[weekday]!)}</span></span
      >
    {/each}
  </div>
  <div class="foot">
    <span class="peak">
      {#if peak}Peak: {weekdayName(peak.weekday, "short")} {hourLabel(peak.hour)} · {formatHeatAmount(
          metric,
          heatValue(peak, metric),
        )}{/if}
    </span>
    <HeatLegend {metric} />
  </div>
  <div class="visually-hidden">
    <table>
      <caption>{HEAT_LABELS[metric]} by weekday and hour of day.</caption>
      <thead>
        <tr>
          <th scope="col">Weekday</th>
          {#each HOURS as hour (hour)}<th scope="col">{hourLabel(hour)}</th>{/each}
        </tr>
      </thead>
      <tbody>
        {#each rows as row (row.long)}
          <tr>
            <th scope="row">{row.long}</th>
            {#each row.values as value, hour (hour)}<td>{formatHeatValue(metric, value)}</td>{/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</figure>

<style>
  .hours {
    display: flex;
    flex: 1;
    flex-direction: column;
    margin: 0;
  }

  /* Weekday rows share any extra card height, so the heatmap matches a taller card beside it. */
  .grid {
    display: grid;
    flex: 1;
    grid-template-columns: 30px repeat(24, minmax(0, 1fr)) 84px;
    grid-template-rows: auto auto repeat(7, 1fr);
    gap: 3px;
    align-items: center;
    font-size: 11px;
    color: var(--text-faint);
  }

  .hour {
    text-align: left;
    white-space: nowrap;
  }

  .weekday {
    line-height: 1;
  }

  /* Square at rest; stretches taller when its row grows. */
  .cell {
    display: block;
    align-self: stretch;
    width: 100%;
    aspect-ratio: 1;
    border-radius: 3px;
    transition: background-color var(--dur-slow) var(--ease);
  }

  .hour-total {
    display: flex;
    align-items: flex-end;
    align-self: end;
    height: 40px;
  }

  .hour-total i,
  .day-total i {
    display: block;
    opacity: 0.8;
    transition:
      height var(--dur-slow) var(--ease),
      width var(--dur-slow) var(--ease);
  }

  .hour-total i {
    width: 100%;
    border-radius: 2px 2px 0 0;
  }

  .day-total {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    overflow: hidden;
    padding-left: 6px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .day-total i {
    flex: none;
    height: 8px;
    border-radius: 0 2px 2px 0;
  }

  .day-value {
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .foot {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    margin-top: var(--space-3);
  }

  .peak {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
