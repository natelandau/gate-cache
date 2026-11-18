<!--
  @component
  A GitHub-style activity calendar: one cell per day, weeks as columns, Sunday through
  Saturday as rows. Cells are colored on the metric's ramp, scaled to the busiest visible day.
  Each cell's tooltip names the date and value, and a hidden table lists the same data.

  With `onselect`, each day is a toggle button with one tab stop for the grid. Click picks a
  day, Shift+click extends from the last picked day, and clicking the only picked day clears
  it. Arrow keys move by day (up and down) and week (left and right), Enter or Space picks,
  Shift+Arrow extends, and Escape clears. Picked days get an inset ring and the others dim.

  Props:
  - `days`: one bucket per day with gaps already filled, in order; `day` is a local
    `YYYY-MM-DD` date
  - `metric`: which value to show and which ramp to use
  - `selected`: the picked days, if any
  - `onselect`: called with the new span, or undefined to clear; omit for a static calendar
-->
<script lang="ts">
  import { tick } from "svelte";
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
  import { createDayCursor } from "../daycursor.svelte";
  import { inSpan, spanOf, toggleDay, type DaySpan } from "../selection";
  import HeatLegend from "./HeatLegend.svelte";

  interface Props {
    days: DayBucket[];
    metric: HeatMetric;
    selected?: DaySpan;
    onselect?: (span: DaySpan | undefined) => void;
  }

  let { days, metric, selected, onselect }: Props = $props();

  interface Cell {
    bucket: DayBucket;
    date: Date;
    index: number;
  }

  // Rows are weekdays and columns are weeks, so Left and Right move a week.
  const STEPS = { ArrowUp: -1, ArrowDown: 1, ArrowLeft: -7, ArrowRight: 7 };

  // Until the user moves it, the tab stop is the first picked day, else the latest day.
  const nav = createDayCursor(() => ({ days, selected, onselect }), STEPS);
  let grid: HTMLElement | undefined = $state();

  function pick(index: number, extend: boolean): void {
    const day = days[index]?.day;
    if (!day || !onselect) return;
    const anchor = nav.cursor.anchor;
    const anchorDay = anchor !== null ? days[anchor]?.day : undefined;
    if (extend && anchorDay) {
      onselect(spanOf(anchorDay, day));
      nav.move(index, anchor);
    } else {
      onselect(toggleDay(selected, day));
      nav.move(index, index);
    }
  }

  async function onkeydown(event: KeyboardEvent): Promise<void> {
    // Each cell is a button, so Enter and Space reach its click handler natively.
    if (event.key === "Enter" || event.key === " ") return;
    if (!nav.key(event)) return;
    await tick();
    grid?.querySelector<HTMLElement>(`[data-index="${nav.cursor.at}"]`)?.focus();
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
    const cells: (Cell | null)[] = days.map((bucket, index) => ({ bucket, date: localDate(bucket.day), index }));
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
  <div class="scroll" aria-hidden={onselect ? undefined : "true"}>
    <div class="weekdays" aria-hidden="true">
      <span></span>
      {#each dayLabels as label, index (index)}<span>{label}</span>{/each}
    </div>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="grid"
      role={onselect ? "group" : undefined}
      aria-label={onselect ? "Pick days to scope the page" : undefined}
      onkeydown={onselect ? onkeydown : undefined}
      bind:this={grid}
    >
      {#each weeks as week (week.key)}
        <span class="month" aria-hidden="true">{week.month}</span>
        {#each week.cells as cell, index (index)}
          {#if cell}
            {@const value = heatValue(cell.bucket, metric)}
            {@const date = dateLong.format(cell.date)}
            {@const text = `${HEAT_LABELS[metric]}: ${formatHeatValue(metric, value)}`}
            {@const title = `${date}\n${text}`}
            {#if onselect}
              {@const on = inSpan(selected, cell.bucket.day)}
              <button
                type="button"
                class="cell"
                class:selected={on}
                class:dimmed={nav.picked !== null && !on}
                style:background={heatColor(metric, heatStep(value, max))}
                {title}
                aria-label="{date}, {text}"
                aria-pressed={on}
                tabindex={cell.index === nav.cursor.at ? 0 : -1}
                data-index={cell.index}
                onclick={(event) => pick(cell.index, event.shiftKey)}
              ></button>
            {:else}
              <span class="cell" style:background={heatColor(metric, heatStep(value, max))} {title}></span>
            {/if}
          {:else}
            <span class="cell pad" aria-hidden="true"></span>
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

  button.cell {
    padding: 0;
    border: 0;
    cursor: pointer;
  }

  button.cell:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: 1px;
  }

  /* A ring, not a color, marks a picked day, so the ramp color stays readable. */
  .cell.selected {
    box-shadow: inset 0 0 0 2px var(--text);
  }

  .cell.dimmed {
    opacity: 0.35;
  }

  @media (prefers-reduced-motion: no-preference) {
    .cell.dimmed {
      transition: opacity 120ms ease-out;
    }
  }
</style>
