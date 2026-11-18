<!--
  @component
  When gates run: a 7 by 24 grid with weekdays (Sunday first) as rows and local hours as
  columns. Cells are colored on the metric's ramp, scaled to the busiest hour. Each cell's
  tooltip names the weekday, hour, and value, and a hidden table lists the same data.

  With `href`, each cell with a value is a link, and the grid has one tab stop: arrow keys move
  between linked cells and Enter follows the focused one.

  Props:
  - `cells`: the hourly buckets; a missing weekday and hour counts as zero
  - `metric`: which value to show and which ramp to use
  - `href`: optional link for a weekday and hour, such as Activity filtered to the runs the
    metric counts there
-->
<script lang="ts">
  import { tick } from "svelte";
  import type { HourCell } from "../api";
  import {
    formatHeatValue,
    HEAT_LABELS,
    heatColor,
    heatStep,
    heatValue,
    hourLabel,
    METRIC_COLORS,
    nextActive,
    weekdayName,
    type HeatMetric,
  } from "../heat";
  import { hourTotals, peakCell, weekdayTotals } from "../hourly";
  import HeatLegend from "./HeatLegend.svelte";

  interface Props {
    cells: HourCell[];
    metric: HeatMetric;
    href?: (weekday: number, hour: number) => string;
  }

  let { cells, metric, href }: Props = $props();

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

  // Cells are numbered weekday * 24 + hour, so Up and Down move a day.
  const STEPS = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -24, ArrowDown: 24 };
  let moved: number | null = $state(null);
  let grid: HTMLElement | undefined = $state();

  // A cell whose shown value is zero stands for no runs, so it gets no link.
  const linked = $derived(rows.flatMap((row) => row.values.map((value) => value > 0)));
  const focusAt = $derived(moved !== null && linked[moved] ? moved : (nextActive(0, 1, linked) ?? -1));

  async function onkeydown(event: KeyboardEvent): Promise<void> {
    // Arrows keep moving the same way past hours with no runs; Home and End search inward.
    // Enter follows the focused link natively.
    let start: number;
    let step: number;
    if (event.key === "Home") [start, step] = [0, 1];
    else if (event.key === "End") [start, step] = [167, -1];
    else if (Object.hasOwn(STEPS, event.key)) {
      step = STEPS[event.key as keyof typeof STEPS];
      start = focusAt + step;
    } else return;
    event.preventDefault();
    const next = nextActive(start, step, linked);
    if (next === null) return;
    moved = next;
    await tick();
    grid?.querySelector<HTMLElement>(`[data-index="${next}"]`)?.focus();
  }
</script>

<figure class="hours">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="grid"
    aria-hidden={href ? undefined : "true"}
    role={href ? "group" : undefined}
    aria-label={href ? "Open the runs of a weekday and hour" : undefined}
    onkeydown={href ? onkeydown : undefined}
    bind:this={grid}
  >
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
        {@const index = weekday * 24 + hour}
        {#if href && linked[index]}
          <a
            class="cell"
            href={href(weekday, hour)}
            style:background={heatColor(metric, heatStep(value, max))}
            {title}
            aria-label="{row.long} {hourLabel(hour)}, {text}. Open in Activity"
            tabindex={index === focusAt ? 0 : -1}
            data-index={index}
            onfocus={() => (moved = index)}
          ></a>
        {:else}
          <span class="cell" style:background={heatColor(metric, heatStep(value, max))} {title}></span>
        {/if}
      {/each}
      <span class="day-total" aria-hidden="true"
        ><i style:width="{weekdayMax ? (byWeekday[weekday]! / weekdayMax) * 28 : 0}px" style:background={METRIC_COLORS[metric]}
        ></i><span class="day-value">{formatHeatValue(metric, byWeekday[weekday]!)}</span></span
      >
    {/each}
  </div>
  <div class="foot">
    <span class="peak">
      {#if peak}Peak: {weekdayName(peak.weekday, "short")} {hourLabel(peak.hour)} · {formatHeatValue(metric, heatValue(peak, metric))}
        {HEAT_LABELS[metric].toLowerCase()}{/if}
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
    margin: 0;
  }

  .grid {
    display: grid;
    grid-template-columns: 30px repeat(24, minmax(0, 1fr)) 84px;
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

  .cell {
    display: block;
    aspect-ratio: 1;
    border-radius: 3px;
    transition: background-color var(--dur-slow) var(--ease);
  }

  a.cell {
    transition:
      background-color var(--dur-slow) var(--ease),
      box-shadow var(--dur-fast) var(--ease);
  }

  a.cell:hover {
    box-shadow: inset 0 0 0 1.5px var(--text);
  }

  a.cell:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: 1px;
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
