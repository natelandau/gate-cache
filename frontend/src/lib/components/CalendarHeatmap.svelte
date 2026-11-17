<!--
  @component
  A GitHub-style activity calendar: one cell per day, weeks as columns, Sunday through
  Saturday as rows. Cells are colored on the metric's ramp, scaled to the busiest visible day.
  Each cell's tooltip names the date and value, and a hidden table lists the same data.

  Props:
  - `days`: one bucket per day with gaps already filled, in order; `day` is a local
    `YYYY-MM-DD` date
  - `metric`: which value to show and which ramp to use
-->
<script lang="ts">
  import type { DayBucket } from "../fill";
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
    days: DayBucket[];
    metric: HeatMetric;
  }

  let { days, metric }: Props = $props();

  interface Cell {
    bucket: DayBucket;
    date: Date;
  }

  interface Week {
    key: number;
    month: string;
    cells: (Cell | null)[];
  }

  const dateLong = new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  // Day keys are local calendar dates, so build local dates rather than parsing as UTC.
  function localDate(day: string): Date {
    const [year = 1970, month = 1, date = 1] = day.split("-").map(Number);
    return new Date(year, month - 1, date);
  }

  // Only Mon, Wed, and Fri get a label to keep the column narrow.
  const dayLabels = [0, 1, 2, 3, 4, 5, 6].map((weekday) =>
    weekday % 2 === 1 && weekday < 6 ? weekdayName(weekday, "short") : "",
  );

  const max = $derived(Math.max(0, ...days.map((bucket) => heatValue(bucket, metric))));

  const weeks = $derived.by(() => {
    const cells: (Cell | null)[] = days.map((bucket) => ({ bucket, date: localDate(bucket.day) }));
    const lead = cells[0]?.date.getDay() ?? 0;
    const padded = [...Array<null>(lead).fill(null), ...cells];
    while (padded.length % 7 !== 0) padded.push(null);
    const result: Week[] = [];
    let lastMonth = -1;
    for (let start = 0; start < padded.length; start += 7) {
      const week = padded.slice(start, start + 7);
      const first = week.find((cell) => cell !== null);
      const month = first ? first.date.getMonth() : -1;
      const label =
        first && month !== lastMonth ? first.date.toLocaleString(undefined, { month: "short" }) : "";
      lastMonth = month;
      result.push({ key: start, month: label, cells: week });
    }
    return result;
  });

  const active = $derived(days.filter((bucket) => heatValue(bucket, metric) > 0));
</script>

<figure class="calendar">
  <div class="scroll" aria-hidden="true">
    <div class="weekdays">
      <span></span>
      {#each dayLabels as label, index (index)}<span>{label}</span>{/each}
    </div>
    <div class="grid">
      {#each weeks as week (week.key)}
        <span class="month">{week.month}</span>
        {#each week.cells as cell, index (index)}
          {#if cell}
            {@const value = heatValue(cell.bucket, metric)}
            <span
              class="cell"
              style:background={heatColor(metric, heatStep(value, max))}
              title="{dateLong.format(cell.date)}&#10;{HEAT_LABELS[metric]}: {formatHeatValue(metric, value)}"
            ></span>
          {:else}
            <span class="cell pad"></span>
          {/if}
        {/each}
      {/each}
    </div>
  </div>
  <HeatLegend {metric} />
  <!-- A table caption renders outside the table box, so the wrapper does the hiding. -->
  <div class="visually-hidden">
    <table>
      <caption>
        {HEAT_LABELS[metric]} per day for {days.length} days. Days with none are left out.
      </caption>
      <thead>
        <tr>
          <th scope="col">Date</th>
          <th scope="col">{HEAT_LABELS[metric]}</th>
        </tr>
      </thead>
      <tbody>
        {#each active as bucket (bucket.day)}
          <tr>
            <th scope="row">{dateLong.format(localDate(bucket.day))}</th>
            <td>{formatHeatValue(metric, heatValue(bucket, metric))}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</figure>

<style>
  .calendar {
    margin: 0;
  }

  .scroll {
    display: flex;
    gap: 6px;
    overflow-x: auto;
  }

  .weekdays,
  .grid {
    display: grid;
    grid-template-rows: 14px repeat(7, 12px);
    gap: 3px;
    font-size: var(--text-xs);
    color: var(--text-faint);
  }

  .weekdays span {
    line-height: 12px;
  }

  .grid {
    grid-auto-flow: column;
    grid-auto-columns: 12px;
  }

  .month {
    width: 12px;
    height: 14px;
    overflow: visible;
    white-space: nowrap;
    line-height: 14px;
  }

  .cell {
    width: 12px;
    height: 12px;
    border-radius: 2px;
  }
</style>
