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
    formatHeatValue,
    HEAT_LABELS,
    heatColor,
    heatStep,
    heatValue,
    weekdayName,
    type HeatMetric,
  } from "../heat";
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

  function hourLabel(hour: number): string {
    return `${String(hour).padStart(2, "0")}:00`;
  }
</script>

<figure class="hours">
  <div class="grid" aria-hidden="true">
    <span></span>
    {#each HOURS as hour (hour)}<span class="hour">{hour % 3 === 0 ? hour : ""}</span>{/each}
    {#each rows as row (row.long)}
      <span class="weekday">{row.short}</span>
      {#each row.values as value, hour (hour)}
        <span
          class="cell"
          style:background={heatColor(metric, heatStep(value, max))}
          title="{row.short} {hourLabel(hour)}&#10;{HEAT_LABELS[metric]}: {formatHeatValue(metric, value)}"
        ></span>
      {/each}
    {/each}
  </div>
  <HeatLegend {metric} />
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
    margin: 0;
  }

  .grid {
    display: grid;
    grid-template-columns: 28px repeat(24, minmax(0, 1fr));
    gap: 2px;
    font-size: var(--text-xs);
    color: var(--text-faint);
  }

  .hour {
    text-align: left;
    white-space: nowrap;
  }

  .weekday {
    line-height: 18px;
  }

  .cell {
    height: 18px;
    border-radius: 2px;
  }
</style>
