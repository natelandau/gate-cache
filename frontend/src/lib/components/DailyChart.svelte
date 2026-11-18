<!--
  @component
  Daily time saved as tall bars over a short panel of daily failures. Both panels share one day
  axis, so hovering a day highlights it in both and shows one tooltip with both values. The two
  measures have different units, so each panel has its own y scale.

  With `onselect`, days can be picked: click a day, or drag across days for a range. Clicking
  the only picked day clears it. The chart takes focus as one control: Left and Right move a
  cursor through the days, Enter or Space picks, Shift+Arrow extends, and
  Escape clears. A box outlines the picked days and the others are washed out.

  Props:
  - `days`: one bucket per day with gaps already filled, in order
  - `selected`: the picked days, if any
  - `onselect`: called with the new span, or undefined to clear; omit for a static chart
-->
<script lang="ts">
  import type { ChartState } from "layerchart";
  import { BarChart, Bars, Tooltip } from "layerchart/svg";
  import { dailyScale } from "../daily";
  import type { DayBucket } from "../fill";
  import { formatCount, formatDuration, formatLongDay, formatShortDay, plural } from "../format";
  import { createDayPick } from "../daypick.svelte";
  import { valueParts } from "../sparkline";
  import ChartTooltip from "./ChartTooltip.svelte";
  import DayPicker from "./DayPicker.svelte";
  import type { DaySpan } from "../selection";

  interface Props {
    days: DayBucket[];
    selected?: DaySpan;
    onselect?: (span: DaySpan | undefined) => void;
  }

  let { days, selected, onselect }: Props = $props();

  interface Row extends DayBucket {
    savedSpan: [number, number];
    failSpan: [number, number];
  }

  // Both panels live on one y scale from 0 to 1, so one band scale and one tooltip serve both.
  const scale = $derived(dailyScale(days));
  const totalFailures = $derived(days.reduce((sum, d) => sum + d.failures, 0));
  const totalSaved = $derived(days.reduce((sum, d) => sum + d.saved, 0));
  const activeDays = $derived(days.filter((d) => d.runs > 0));

  const rows = $derived(
    days.map(
      (d): Row => ({
        ...d,
        savedSpan: [scale.savedY(0), scale.savedY(d.saved)],
        failSpan: [0, scale.failY(d.failures)],
      }),
    ),
  );

  const tickLabels = $derived(new Map(scale.ticks.map((t) => [t.value, t.label])));

  const padding = { top: 8, right: 4, bottom: 20, left: 44 };
  const BAND_PADDING = 0.25;

  const pick = createDayPick(() => ({ days, selected, onselect }), padding, BAND_PADDING);

  function dayText(day: DayBucket): string {
    return `${formatLongDay(day.day)}: ${formatDuration(day.saved)} saved, ${plural(day.failures, "failure", "failures")}`;
  }
  const savedColor = "var(--chart-saved)";
  const failColor = "var(--chart-failures)";
</script>

{#snippet dayTooltip(context: ChartState<Row>)}
  <Tooltip.Root {context} variant="none" motion="none">
    {#snippet children({ data }: { data: Row })}
      <ChartTooltip
        title={formatLongDay(data.day)}
        rows={[
          { color: savedColor, label: "Time saved", value: formatDuration(data.saved) },
          { color: failColor, label: "Failures", value: formatCount(data.failures) },
          { color: "var(--chart-runs)", label: "Runs", value: formatCount(data.runs) },
        ]}
        hint={onselect ? "Click to scope the page to this day" : undefined}
      />
    {/snippet}
  </Tooltip.Root>
{/snippet}

<figure class="daily">
  <figcaption class="top">
    <span class="headline">
      <span class="big"
        >{#each valueParts(formatDuration(totalSaved)) as part, i (i)}{#if part.unit}<span class="u">{part.text}</span
            >{:else}{part.text}{/if}{/each}</span
      >
      <span class="second">saved · <span class="fails">{formatCount(totalFailures)}</span> {totalFailures === 1 ? "failure" : "failures"}</span>
    </span>
    <span class="legend">
      <span><i style:background={savedColor}></i>Time saved</span>
      <span><i style:background={failColor}></i>Failures</span>
    </span>
  </figcaption>
  <!-- Pointer events bubble up from the chart, so its tooltip keeps working under the picker. -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="frame"
    class:pickable={onselect}
    onpointerdown={onselect ? pick.onpointerdown : undefined}
    onpointermove={onselect ? pick.onpointermove : undefined}
    onpointerup={onselect ? pick.onpointerup : undefined}
    onpointercancel={pick.cancel}
    onlostpointercapture={pick.cancel}
  >
  <div class="plot" aria-hidden="true">
    <BarChart
      data={rows}
      x="day"
      y={(d: Row) => d.savedSpan}
      yDomain={[0, 1]}
      bandPadding={BAND_PADDING}
      {padding}
      rule={false}
      grid={{ x: false, y: true, yTicks: scale.gridTicks }}
      props={{
        xAxis: { tickSpacing: 72, tickLength: 3, format: (d: string) => formatShortDay(d) },
        yAxis: {
          ticks: [...tickLabels.keys()],
          tickLength: 0,
          format: (v: number) => tickLabels.get(v) ?? "",
        },
      }}
    >
      {#snippet marks()}
        <Bars y={(d: Row) => d.savedSpan} fill={savedColor} radius={3} strokeWidth={0} />
        <Bars y={(d: Row) => d.failSpan} fill={failColor} radius={3} strokeWidth={0} />
      {/snippet}
      {#snippet tooltip({ context })}{@render dayTooltip(context)}{/snippet}
    </BarChart>
  </div>
  {#if onselect}
    <DayPicker {pick} {days} label={dayText} />
  {/if}
  </div>
  <!-- A table caption renders outside the table box, so the wrapper does the hiding. -->
  <div class="visually-hidden">
    <table>
      <caption>
        Daily totals for {days.length} days: {formatDuration(totalSaved)} saved,
        {formatCount(totalFailures)} failures. Days without runs are left out.
      </caption>
      <thead>
        <tr>
          <th scope="col">Day</th>
          <th scope="col">Time saved</th>
          <th scope="col">Failures</th>
        </tr>
      </thead>
      <tbody>
        {#each activeDays as day (day.day)}
          <tr>
            <th scope="row">{formatLongDay(day.day)}</th>
            <td>{formatDuration(day.saved)}</td>
            <td>{formatCount(day.failures)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</figure>

<style>
  .daily {
    margin: 0;
  }

  .top {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-2) var(--space-4);
    margin-bottom: var(--space-3);
  }

  .headline {
    display: inline-flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--space-3);
  }

  .big {
    font-size: var(--text-headline);
    font-weight: 600;
    line-height: 32px;
    letter-spacing: var(--track-kpi);
  }

  .u {
    margin: 0 3px 0 1px;
    color: var(--text-muted);
    font-size: 0.6em;
    font-weight: 500;
    letter-spacing: 0;
  }

  .u:last-child {
    margin-right: 0;
  }

  .second {
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  .fails {
    color: var(--danger);
    font-size: var(--text-lg);
    font-weight: 600;
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .legend span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .legend i {
    width: 8px;
    height: 8px;
    border-radius: 2px;
  }

  .frame {
    position: relative;
  }

  .pickable {
    cursor: pointer;
    touch-action: pan-y;
    user-select: none;
  }

  .plot {
    height: 260px;
  }

  .daily :global(.lc-axis-tick-label),
  .daily :global(text) {
    font-size: var(--text-xs);
    fill: var(--text-faint);
  }

  .daily :global(.lc-grid-line),
  .daily :global(.lc-grid line) {
    stroke: var(--chart-grid);
  }
</style>
