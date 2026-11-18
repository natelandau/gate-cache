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
  import { BarChart, Bars, Text, Tooltip } from "layerchart/svg";
  import { bandIndexAt, bandInset, dailyScale, FAIL_TOP } from "../daily";
  import type { DayBucket } from "../fill";
  import { formatCount, formatDuration, plural } from "../format";
  import { createDayCursor } from "../daycursor.svelte";
  import { spanAt, toggleDay, type DaySpan } from "../selection";

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

  const dayLabel = new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
  const dayLong = new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });

  // Day keys are calendar dates, so format them as UTC to avoid shifting by the local offset.
  function shortDay(day: string): string {
    return dayLabel.format(new Date(`${day}T00:00:00Z`));
  }

  function longDay(day: string): string {
    return dayLong.format(new Date(`${day}T00:00:00Z`));
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

  // The top padding holds the time-saved label, clear of the bars below it.
  const padding = { top: 18, right: 4, bottom: 20, left: 52 };
  const BAND_PADDING = 0.25;

  const nav = createDayCursor(() => ({ days, selected, onselect }), { ArrowLeft: -1, ArrowRight: 1 });
  // A drag in progress, shown in place of the picked days until the pointer is released.
  let drag = $state<{ anchor: number; at: number } | null>(null);
  const shown = $derived<[number, number] | null>(
    drag ? [Math.min(drag.anchor, drag.at), Math.max(drag.anchor, drag.at)] : nav.picked,
  );
  let listbox: HTMLElement | undefined = $state();
  // The plot's box, read once per drag rather than on every pointer move.
  let box: DOMRect | null = null;

  // A drag in progress clamps to the plot, so a fast drag past either end reaches the edge day.
  function indexAt(event: PointerEvent, clamp = false): number | null {
    if (!box) return null;
    const width = box.width - padding.left - padding.right;
    const fraction = (event.clientX - box.left - padding.left) / width;
    return bandIndexAt(clamp ? Math.min(1, Math.max(0, fraction)) : fraction, days.length, BAND_PADDING);
  }

  function onpointerdown(event: PointerEvent): void {
    if (event.button !== 0) return;
    box = (event.currentTarget as HTMLElement).getBoundingClientRect();
    const index = indexAt(event);
    if (index === null) return;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    drag = { anchor: index, at: index };
  }

  function onpointermove(event: PointerEvent): void {
    if (!drag) return;
    const index = indexAt(event, true);
    if (index !== null && index !== drag.at) drag = { anchor: drag.anchor, at: index };
  }

  function onpointerup(): void {
    if (!drag) return;
    const { anchor, at } = drag;
    drag = null;
    nav.move(at, anchor);
    const day = days[at]?.day;
    if (anchor === at && day) onselect?.(toggleDay(selected, day));
    else onselect?.(spanAt(days, [Math.min(anchor, at), Math.max(anchor, at)]));
    // Arrow keys continue from the day just picked without tabbing in first.
    listbox?.focus({ preventScroll: true });
  }

  const uid = $props.id();

  function dayText(day: DayBucket): string {
    return `${longDay(day.day)}: ${formatDuration(day.saved)} saved, ${plural(day.failures, "failure", "failures")}`;
  }
  const inset = $derived(bandInset(days.length, BAND_PADDING));
  const savedColor = "var(--chart-saved)";
  const failColor = "var(--chart-failures)";
</script>

{#snippet dayTooltip(context: ChartState<Row>)}
  <Tooltip.Root {context}>
    {#snippet children({ data }: { data: Row })}
      <Tooltip.Header value={longDay(data.day)} />
      <Tooltip.List>
        <Tooltip.Item
          label="Time saved"
          value={formatDuration(data.saved)}
          color={savedColor}
          valueAlign="right"
        />
        <Tooltip.Item
          label="Failures"
          value={formatCount(data.failures)}
          color={failColor}
          valueAlign="right"
        />
      </Tooltip.List>
    {/snippet}
  </Tooltip.Root>
{/snippet}

<figure class="daily">
  <figcaption class="legend">
    <span><i style:background={savedColor}></i>Time saved per day</span>
    <span><i style:background={failColor}></i>Failures per day</span>
  </figcaption>
  <!-- Pointer events bubble up from the chart, so its tooltip keeps working under the picker. -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="frame"
    class:pickable={onselect}
    onpointerdown={onselect ? onpointerdown : undefined}
    onpointermove={onselect ? onpointermove : undefined}
    onpointerup={onselect ? onpointerup : undefined}
    onpointercancel={() => (drag = null)}
    onlostpointercapture={() => (drag = null)}
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
        xAxis: { tickSpacing: 72, tickLength: 3, format: (d: string) => shortDay(d) },
        yAxis: {
          ticks: [...tickLabels.keys()],
          tickLength: 0,
          format: (v: number) => tickLabels.get(v) ?? "",
        },
      }}
    >
      {#snippet marks({ context }: { context: ChartState<Row> })}
        <Bars y={(d: Row) => d.savedSpan} fill={savedColor} radius={2} strokeWidth={0} />
        <Bars y={(d: Row) => d.failSpan} fill={failColor} radius={2} strokeWidth={0} />
        <!-- Each label sits just above its band: in the top padding and in the gap between bands,
             where no bars or tick labels reach. -->
        <Text
          class="panel-label"
          x={0}
          y={context.yScale(1) - 4}
          value="Time saved"
          verticalAnchor="end"
        />
        <Text
          class="panel-label"
          x={0}
          y={context.yScale(FAIL_TOP) - 4}
          value="Failures"
          verticalAnchor="end"
        />
      {/snippet}
      {#snippet tooltip({ context })}{@render dayTooltip(context)}{/snippet}
    </BarChart>
  </div>
  {#if onselect}
    <div
      class="picker"
      role="listbox"
      aria-multiselectable="true"
      aria-label="Pick days to scope the page"
      aria-describedby="{uid}-help"
      aria-activedescendant={days.length ? `${uid}-${nav.cursor.at}` : undefined}
      tabindex="0"
      bind:this={listbox}
      style:top="{padding.top}px"
      style:bottom="{padding.bottom}px"
      style:left="{padding.left}px"
      style:right="{padding.right}px"
      onkeydown={(event) => nav.key(event)}
    >
      <div class="columns" style:margin-inline="{inset}%">
        {#each days as day, index (day.day)}
          {@const on = shown !== null && index >= shown[0] && index <= shown[1]}
          <span
            id="{uid}-{index}"
            role="option"
            aria-selected={on}
            aria-label={dayText(day)}
            class="column"
            class:selected={on}
            class:dimmed={shown !== null && !on}
            class:cursor={index === nav.cursor.at}
          ></span>
        {/each}
        {#if shown}
          <span
            class="range"
            aria-hidden="true"
            style:left="{(shown[0] / days.length) * 100}%"
            style:width="{((shown[1] - shown[0] + 1) / days.length) * 100}%"
          ></span>
        {/if}
      </div>
    </div>
    <p id="{uid}-help" class="visually-hidden">
      Arrow keys move between days. Enter or Space picks a day, Shift with an arrow key extends
      the pick, and Escape clears it.
    </p>
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
            <th scope="row">{longDay(day.day)}</th>
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

  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
    font-size: var(--text-xs);
    color: var(--text-muted);
    margin-bottom: var(--space-1);
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

  /* Visual only: pointer input goes to the chart below, so its tooltip keeps working. */
  .picker {
    position: absolute;
    pointer-events: none;
    border-radius: 2px;
  }

  .picker:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: 2px;
  }

  .columns {
    position: relative;
    display: flex;
    height: 100%;
  }

  .column {
    flex: 1;
    min-width: 0;
  }

  .column.dimmed {
    background: var(--surface);
    opacity: 0.65;
  }

  .picker:focus-visible .column.cursor {
    outline: 1px dashed var(--focus);
    outline-offset: -1px;
  }

  .range {
    position: absolute;
    top: 0;
    bottom: 0;
    border: 2px solid var(--text);
    border-radius: 2px;
  }

  .daily :global(.lc-axis-tick-label),
  .daily :global(text) {
    font-size: var(--text-xs);
    fill: var(--text-muted);
  }

  .daily :global(.panel-label) {
    fill: var(--text-muted);
    font-weight: 600;
  }

  .daily :global(.lc-grid-line),
  .daily :global(.lc-grid line) {
    stroke: var(--chart-grid);
  }
</style>
