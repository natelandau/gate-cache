<!--
  @component
  An activity calendar: one cell per day, colored on the metric's ramp and scaled to the
  busiest visible day. Up to six weeks show as a wall calendar, Monday-first weeks as rows with
  large cells; longer ranges show weeks as columns and Sunday through Saturday as rows. Cells
  grow to fill the width. Each cell's tooltip names the date and value, and a hidden table
  lists the same data.

  With `onselect`, each day is a toggle button with one tab stop for the grid. Click picks a
  day, Shift+click extends from the last picked day, and clicking the only picked day clears
  it. Arrow keys move by day and by week along the grid's axes, Enter or Space picks,
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
  import { calendarLayout, monthGrid } from "../calendar";
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

  const layout = $derived(calendarLayout(days.map((d) => d.day)));
  // Arrows follow the grid: in week rows Up and Down move a week, in week columns Left and
  // Right do. Getters, so the cursor reads the current layout on each key.
  const STEPS = {
    get ArrowUp() {
      return layout === "month" ? -7 : -1;
    },
    get ArrowDown() {
      return layout === "month" ? 7 : 1;
    },
    get ArrowLeft() {
      return layout === "month" ? -1 : -7;
    },
    get ArrowRight() {
      return layout === "month" ? 1 : 7;
    },
  };

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

  const MONDAY_FIRST = [1, 2, 3, 4, 5, 6, 0].map((weekday) => weekdayName(weekday, "short").slice(0, 1));
  const rowsOfWeeks = $derived.by(() => {
    if (layout !== "month") return [];
    const byDay = new Map(days.map((bucket, index) => [bucket.day, index]));
    return monthGrid(days.map((d) => d.day)).map((week) => {
      const cells = week.map((day): Cell | null => {
        const index = day === null ? undefined : byDay.get(day);
        const bucket = index === undefined ? undefined : days[index];
        return bucket && index !== undefined ? { bucket, date: localDate(bucket.day), index } : null;
      });
      const first = cells.find((cell) => cell !== null);
      const label = first ? first.date.toLocaleString(undefined, { month: "short", day: "numeric" }) : "";
      return { key: week.find((d) => d !== null) ?? "", label, cells };
    });
  });
</script>

{#snippet dayCell(cell: Cell | null)}
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
{/snippet}

<figure class="calendar layout-{layout}">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="grid"
    aria-hidden={onselect ? undefined : "true"}
    role={onselect ? "group" : undefined}
    aria-label={onselect ? "Pick days to scope the page" : undefined}
    onkeydown={onselect ? onkeydown : undefined}
    bind:this={grid}
  >
    {#if layout === "month"}
      <span aria-hidden="true"></span>
      {#each MONDAY_FIRST as letter, index (index)}<span class="weekday" aria-hidden="true">{letter}</span>{/each}
      {#each rowsOfWeeks as week (week.key)}
        <span class="week-label" aria-hidden="true">{week.label}</span>
        {#each week.cells as cell, index (index)}{@render dayCell(cell)}{/each}
      {/each}
    {:else}
      <span aria-hidden="true"></span>
      {#each dayLabels as label, index (index)}<span class="weekday" aria-hidden="true">{label}</span>{/each}
      {#each weeks as week (week.key)}
        <span class="month" aria-hidden="true">{week.month}</span>
        {#each week.cells as cell, index (index)}{@render dayCell(cell)}{/each}
      {/each}
    {/if}
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

  .grid {
    display: grid;
    gap: 5px;
    color: var(--text-faint);
    font-size: 11px;
  }

  /* Wall calendar: a label column, then seven weekday columns that share the width. */
  .layout-month .grid {
    grid-template-columns: max-content repeat(7, minmax(0, 1fr));
    align-items: center;
    max-width: 480px;
  }

  .layout-month .weekday {
    text-align: center;
  }

  .week-label {
    padding-right: var(--space-1);
    text-align: right;
    white-space: nowrap;
  }

  /* Week columns: weekday labels first, then one column per week, filling the width. */
  .layout-weeks .grid {
    grid-template-rows: 14px repeat(7, auto);
    grid-auto-flow: column;
    grid-template-columns: max-content;
    grid-auto-columns: minmax(10px, 1fr);
    gap: 3px;
    overflow-x: auto;
  }

  .layout-weeks .weekday {
    padding-right: var(--space-1);
    line-height: 1;
  }

  .month {
    height: 14px;
    overflow: visible;
    white-space: nowrap;
    line-height: 14px;
  }

  .cell {
    display: block;
    aspect-ratio: 1;
    width: 100%;
    border-radius: 5px;
  }

  .layout-weeks .cell {
    border-radius: 3px;
  }

  button.cell {
    padding: 0;
    border: 0;
    cursor: pointer;
    transition: opacity var(--dur-fast) var(--ease);
  }

  button.cell:hover {
    box-shadow: inset 0 0 0 1.5px var(--text);
  }

  button.cell:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: 1px;
  }

  .cell.pad {
    visibility: hidden;
  }

  /* A ring, not a color, marks a picked day, so the ramp color stays readable. */
  .cell.selected {
    box-shadow: inset 0 0 0 2px var(--text);
  }

  .cell.dimmed {
    opacity: 0.35;
  }
</style>
