<!--
  @component
  Daily runs as tall bars over a short panel of daily failures, with time saved in the headline
  and the tooltip. Both panels share one day
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
  import { barMotion } from "../motion";
  import type { ChartState } from "layerchart";
  import { BarChart, Bars, Tooltip } from "layerchart/svg";
  import { dailyScale } from "../daily";
  import { METRIC_COLORS } from "../heat";
  import type { DayBucket } from "../fill";
  import { formatCount, formatDuration, formatLongDay, formatShortDay, plural } from "../format";
  import { createDayPick } from "../daypick.svelte";
  import ChartTooltip from "./ChartTooltip.svelte";
  import DayPicker from "./DayPicker.svelte";
  import UnitValue from "./UnitValue.svelte";
  import { PICK_DAY_HINT, type DaySpan } from "../selection";

  interface Props {
    days: DayBucket[];
    selected?: DaySpan;
    onselect?: (span: DaySpan | undefined) => void;
  }

  let { days, selected, onselect }: Props = $props();

  interface Row extends DayBucket {
    runsSpan: [number, number];
    failSpan: [number, number];
  }

  // Both panels live on one y scale from 0 to 1, so one band scale and one tooltip serve both.
  const scale = $derived(dailyScale(days));
  const totalFailures = $derived(days.reduce((sum, d) => sum + d.failures, 0));
  const totalSaved = $derived(days.reduce((sum, d) => sum + d.saved, 0));
  const totalRuns = $derived(days.reduce((sum, d) => sum + d.runs, 0));
  const activeDays = $derived(days.filter((d) => d.runs > 0));

  const rows = $derived(
    days.map(
      (d): Row => ({
        ...d,
        runsSpan: [scale.runsY(0), scale.runsY(d.runs)],
        failSpan: [0, scale.failY(d.failures)],
      }),
    ),
  );

  const tickLabels = $derived(new Map(scale.ticks.map((t) => [t.value, t.label])));

  const padding = { top: 8, right: 4, bottom: 20, left: 44 };
  const BAND_PADDING = 0.25;

  const pick = createDayPick(() => ({ days, selected, onselect }), padding, BAND_PADDING);

  function dayText(day: DayBucket): string {
    return `${formatLongDay(day.day)}: ${plural(day.runs, "gate call", "gate calls")}, ${plural(day.failures, "failure", "failures")}, ${formatDuration(day.saved)} saved by cache`;
  }
  const runsColor = METRIC_COLORS.runs;
  const failColor = METRIC_COLORS.fail;
</script>

{#snippet dayTooltip(context: ChartState<Row>)}
  <Tooltip.Root {context} variant="none" motion="none">
    {#snippet children({ data }: { data: Row })}
      <ChartTooltip
        title={formatLongDay(data.day)}
        rows={[
          { color: runsColor, label: "Gate calls", value: formatCount(data.runs) },
          { color: failColor, label: "Failures", value: formatCount(data.failures) },
          { label: "Saved by cache", value: formatDuration(data.saved) },
        ]}
        hint={onselect ? PICK_DAY_HINT : undefined}
      />
    {/snippet}
  </Tooltip.Root>
{/snippet}

<figure class="daily">
  <figcaption class="top">
    <span class="headline">
      <span class="big">{formatCount(totalRuns)}</span>
      <span class="second"
        >{totalRuns === 1 ? "gate call" : "gate calls"} · <span class="fails">{formatCount(totalFailures)}</span>
        {totalFailures === 1 ? "failure" : "failures"} · <UnitValue value={formatDuration(totalSaved)} /> saved by cache</span
      >
    </span>
    <span class="legend">
      <span><i style:background={runsColor}></i>Gate calls</span>
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
      y={(d: Row) => d.runsSpan}
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
        <Bars y={(d: Row) => d.runsSpan} fill={runsColor} radius={3} strokeWidth={0} motion={barMotion()} />
        <Bars y={(d: Row) => d.failSpan} fill={failColor} radius={3} strokeWidth={0} motion={barMotion()} />
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
        Daily totals for {days.length} days: {formatCount(totalRuns)} gate calls,
        {formatCount(totalFailures)} failures, {formatDuration(totalSaved)} saved by cache. Days
        without calls are left out.
      </caption>
      <thead>
        <tr>
          <th scope="col">Day</th>
          <th scope="col">Gate calls</th>
          <th scope="col">Failures</th>
          <th scope="col">Saved by cache</th>
        </tr>
      </thead>
      <tbody>
        {#each activeDays as day (day.day)}
          <tr>
            <th scope="row">{formatLongDay(day.day)}</th>
            <td>{formatCount(day.runs)}</td>
            <td>{formatCount(day.failures)}</td>
            <td>{formatDuration(day.saved)}</td>
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


  .second {
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  .second :global(.u) {
    font-size: 1em;
    font-weight: 400;
    margin: 0;
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


</style>
