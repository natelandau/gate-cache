<!--
  @component
  Daily time spent as one bar per day, stacked by gate with the largest gate at the bottom.
  Hovering a segment or a legend entry highlights that gate and dims the rest, since
  neighboring shades are close. A legend entry for a gate is a button that opens it.

  With `onselect`, days can be picked exactly as on `DailyChart`: click, drag, or the keyboard.

  Props:
  - `rows`: one stacked row per day with gaps already filled, in order, from `spentRows`
  - `series`: the stacked parts, bottom first, from `spentSeries`
  - `selected`: the picked days, if any
  - `onselect`: called with the new span, or undefined to clear; omit for a static chart
  - `onpickgate`: called with a gate whose legend entry was clicked
-->
<script lang="ts">
  import { barMotion } from "../motion";
  import type { ChartState } from "layerchart";
  import { BarChart, Bars, Tooltip } from "layerchart/svg";
  import type { SpentGate } from "../api";
  import { createDayPick } from "../daypick.svelte";
  import { durationTicks, formatAxisDuration, formatDuration, formatLongDay, formatShortDay } from "../format";
  import { PICK_DAY_HINT, type DaySpan } from "../selection";
  import { spentTotals, type SpentRow, type SpentSeries } from "../spent";
  import ChartTooltip from "./ChartTooltip.svelte";
  import DayPicker from "./DayPicker.svelte";

  interface Props {
    rows: SpentRow[];
    series: SpentSeries[];
    selected?: DaySpan;
    onselect?: (span: DaySpan | undefined) => void;
    onpickgate?: (gate: SpentGate) => void;
  }

  let { rows, series, selected, onselect, onpickgate }: Props = $props();

  const ticks = $derived(durationTicks(Math.max(0, ...rows.map((r) => r.total))));
  const top = $derived(Math.max(1, ticks.at(-1) ?? 0));
  const activeRows = $derived(rows.filter((r) => r.total > 0));
  const colorOf = $derived(new Map(series.map((s) => [s.key, s.color])));
  const labelOf = $derived(new Map(series.map((s) => [s.key, s.label])));
  const totals = $derived(spentTotals(series, rows));

  const padding = { top: 8, right: 4, bottom: 20, left: 52 };
  const BAND_PADDING = 0.25;
  const DIM = 0.3;

  const pick = createDayPick(() => ({ days: rows, selected, onselect }), padding, BAND_PADDING);

  /** The series key under the pointer or the focused legend entry, if any. */
  let highlight = $state<string | null>(null);

  function span(row: SpentRow, key: string): [number, number] {
    const segment = row.segments.find((s) => s.key === key);
    return segment ? [segment.start, segment.end] : [0, 0];
  }

  // The tooltip's hit areas sit above the bars, so the hovered segment comes from the pointer
  // position rather than from events on the bars.
  function hoverAt(event: PointerEvent): void {
    const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
    const fy = (event.clientY - box.top - padding.top) / (box.height - padding.top - padding.bottom);
    const index = pick.indexAt(event, box);
    const value = (1 - fy) * top;
    const segment =
      index === null || fy < 0 || fy > 1
        ? undefined
        : rows[index]?.segments.find((s) => s.end > s.start && value >= s.start && value < s.end);
    highlight = segment?.key ?? null;
  }

  function onpointermove(event: PointerEvent): void {
    if (onselect) pick.onpointermove(event);
    hoverAt(event);
  }

  function opacity(key: string): number {
    return highlight === null || highlight === key ? 1 : DIM;
  }

  function parts(row: SpentRow): { key: string; seconds: number }[] {
    return row.segments
      .map((s) => ({ key: s.key, seconds: s.end - s.start }))
      .filter((p) => p.seconds > 0)
      .sort((a, b) => b.seconds - a.seconds);
  }

  function dayText(row: SpentRow): string {
    return `${formatLongDay(row.day)}: ${formatDuration(row.total)} of run time`;
  }
</script>

{#snippet dayTooltip(context: ChartState<SpentRow>)}
  <Tooltip.Root {context} variant="none" motion="none">
    {#snippet children({ data }: { data: SpentRow })}
      <ChartTooltip
        title={formatLongDay(data.day)}
        rows={[
          ...parts(data).map((part) => ({
            color: colorOf.get(part.key),
            label: labelOf.get(part.key) ?? "",
            value: formatDuration(part.seconds),
          })),
          { label: "Total", value: formatDuration(data.total) },
        ]}
        hint={onselect ? PICK_DAY_HINT : undefined}
      />
    {/snippet}
  </Tooltip.Root>
{/snippet}

<figure class="spent">
  <figcaption class="legend">
    {#each totals.items as item (item.key)}
      {#snippet entry()}
        <i style:background={item.color}></i>
        <span class="name" title="{item.name}{item.repo ? ` · ${item.repo}` : ''}"
          >{item.name}{#if item.repo}<span class="repo">{item.repo}</span>{/if}</span
        >
        <span class="total">{formatDuration(item.total)}</span>
      {/snippet}
      {#if item.gate && onpickgate}
        {@const gate = item.gate}
        <button
          type="button"
          class="entry"
          class:faded={opacity(item.key) < 1}
          onclick={() => onpickgate(gate)}
          onpointerenter={() => (highlight = item.key)}
          onpointerleave={() => (highlight = null)}
          onfocus={() => (highlight = item.key)}
          onblur={() => (highlight = null)}
        >
          {@render entry()}
        </button>
      {:else}
        <span
          class="entry"
          class:faded={opacity(item.key) < 1}
          role="presentation"
          onpointerenter={() => (highlight = item.key)}
          onpointerleave={() => (highlight = null)}
        >
          {@render entry()}
        </span>
      {/if}
    {/each}
    <span class="grand"><span>Total</span><span class="total">{formatDuration(totals.total)}</span></span>
  </figcaption>
  <!-- Pointer events bubble up from the chart, so its tooltip keeps working under the picker. -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="frame"
    class:pickable={onselect}
    onpointerdown={onselect ? pick.onpointerdown : undefined}
    {onpointermove}
    onpointerleave={() => (highlight = null)}
    onpointerup={onselect ? pick.onpointerup : undefined}
    onpointercancel={pick.cancel}
    onlostpointercapture={pick.cancel}
  >
    <div class="plot" aria-hidden="true">
      <BarChart
        data={rows}
        x="day"
        y={(d: SpentRow) => [0, d.total]}
        yDomain={[0, top]}
        bandPadding={BAND_PADDING}
        {padding}
        rule={false}
        grid={{ x: false, y: true, yTicks: ticks }}
        props={{
          xAxis: { tickSpacing: 72, tickLength: 3, format: (d: string) => formatShortDay(d) },
          yAxis: { ticks, tickLength: 0, format: (v: number) => formatAxisDuration(v) },
        }}
      >
        {#snippet marks()}
          {#each series as s (s.key)}
            <Bars
              y={(d: SpentRow) => span(d, s.key)}
              fill={s.color}
              opacity={opacity(s.key)}
              radius={0}
              strokeWidth={0}
              motion={barMotion()}
            />
          {/each}
        {/snippet}
        {#snippet tooltip({ context })}{@render dayTooltip(context)}{/snippet}
      </BarChart>
    </div>
    {#if onselect}
      <DayPicker {pick} days={rows} label={dayText} />
    {/if}
  </div>
  <!-- A table caption renders outside the table box, so the wrapper does the hiding. -->
  <div class="visually-hidden">
    <table>
      <caption>
        Run time per day for {rows.length} days: {formatDuration(totals.total)} in all. Days without
        time spent are left out.
      </caption>
      <thead>
        <tr>
          <th scope="col">Day</th>
          <th scope="col">Total</th>
          {#each series as s (s.key)}
            <th scope="col">{s.label}</th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each activeRows as row (row.day)}
          <tr>
            <th scope="row">{formatLongDay(row.day)}</th>
            <td>{formatDuration(row.total)}</td>
            {#each row.segments as segment (segment.key)}
              <td>{formatDuration(segment.end - segment.start)}</td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</figure>

<style>
  .spent {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 240px;
    grid-template-areas: "chart legend";
    gap: var(--space-5);
    margin: 0;
  }

  .legend {
    grid-area: legend;
    display: flex;
    flex-direction: column;
    min-width: 0;
    font-size: var(--text-sm);
  }

  .entry {
    display: grid;
    grid-template-columns: 10px minmax(0, 1fr) auto;
    gap: var(--space-2);
    align-items: center;
    height: 32px;
    padding: 0 var(--space-1);
    border-bottom: 1px solid var(--border-row);
    border-radius: var(--radius-chip);
    color: var(--text);
    text-align: left;
    transition:
      background-color var(--dur-fast) var(--ease),
      opacity var(--dur-fast) var(--ease);
  }

  button.entry {
    width: 100%;
    border-top: 0;
    border-right: 0;
    border-left: 0;
    background: none;
    font: inherit;
    cursor: pointer;
  }

  button.entry:hover {
    background: var(--surface-hover);
  }

  button.entry:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: -2px;
  }

  .entry.faded {
    opacity: 0.5;
  }

  .legend i {
    width: 10px;
    height: 10px;
    border-radius: 2px;
  }

  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .repo {
    margin-left: 5px;
    color: var(--text-muted);
  }

  .total {
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .grand {
    display: flex;
    justify-content: space-between;
    padding: 10px var(--space-1) 0;
    color: var(--text-muted);
  }

  .grand .total {
    color: var(--text);
    font-weight: 600;
  }

  .frame {
    grid-area: chart;
    position: relative;
    min-width: 0;
  }

  .pickable {
    cursor: pointer;
    touch-action: pan-y;
    user-select: none;
  }

  .plot {
    height: 300px;
  }



  @media (max-width: 900px) {
    .spent {
      grid-template-columns: minmax(0, 1fr);
      grid-template-areas: "chart" "legend";
    }
  }
</style>
