<!--
  @component
  Daily time saved as bars, with a short failures strip below on the same day axis. The two
  measures have different units, so each gets its own y scale instead of sharing one.

  Props:
  - `days`: one bucket per day with gaps already filled, in order
-->
<script lang="ts">
  import type { ChartState } from "layerchart";
  import { BarChart, Tooltip } from "layerchart/svg";
  import type { DayBucket } from "../fill";
  import { durationTicks, formatAxisDuration, formatCount, formatDuration } from "../format";

  interface Props {
    days: DayBucket[];
  }

  let { days }: Props = $props();

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

  const savedTicks = $derived(durationTicks(Math.max(0, ...days.map((d) => d.saved))));
  const savedTop = $derived(Math.max(1, savedTicks.at(-1) ?? 0));
  const maxFailures = $derived(Math.max(1, ...days.map((d) => d.failures)));
  const totalFailures = $derived(days.reduce((sum, d) => sum + d.failures, 0));
  const totalSaved = $derived(days.reduce((sum, d) => sum + d.saved, 0));
  const activeDays = $derived(days.filter((d) => d.runs > 0));

  const padding = { top: 10, right: 4, bottom: 4, left: 52 };
  const savedColor = "var(--chart-saved)";
  const failColor = "var(--chart-failures)";
</script>

{#snippet dayTooltip(context: ChartState<DayBucket>)}
  <Tooltip.Root {context}>
    {#snippet children({ data }: { data: DayBucket })}
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
        <Tooltip.Item label="Runs" value={formatCount(data.runs)} valueAlign="right" />
      </Tooltip.List>
    {/snippet}
  </Tooltip.Root>
{/snippet}

<figure class="daily">
  <figcaption class="legend">
    <span><i style:background={savedColor}></i>Time saved per day</span>
    <span><i style:background={failColor}></i>Failures per day</span>
  </figcaption>
  <div class="saved" aria-hidden="true">
    <BarChart
      data={days}
      x="day"
      y="saved"
      yDomain={[0, savedTop]}
      series={[{ key: "saved", label: "Time saved", value: "saved", color: savedColor }]}
      bandPadding={0.25}
      {padding}
      rule={false}
      grid={{ x: false, y: true, yTicks: savedTicks }}
      props={{
        xAxis: { ticks: [], tickLength: 0 },
        yAxis: {
          ticks: savedTicks,
          tickLength: 0,
          format: formatAxisDuration,
        },
        bars: { radius: 2, strokeWidth: 0 },
      }}
    >
      {#snippet tooltip({ context })}{@render dayTooltip(context)}{/snippet}
    </BarChart>
  </div>
  <div class="failures" aria-hidden="true">
    <BarChart
      data={days}
      x="day"
      y="failures"
      yDomain={[0, maxFailures]}
      series={[{ key: "failures", label: "Failures", value: "failures", color: failColor }]}
      bandPadding={0.25}
      padding={{ ...padding, bottom: 20 }}
      rule={false}
      grid={false}
      props={{
        xAxis: {
          tickSpacing: 72,
          tickLength: 3,
          format: (d: string) => shortDay(d),
        },
        yAxis: { ticks: [maxFailures], tickLength: 0, format: (v: number) => formatCount(v) },
        bars: { radius: 2, strokeWidth: 0 },
      }}
    >
      {#snippet tooltip({ context })}{@render dayTooltip(context)}{/snippet}
    </BarChart>
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
          <th scope="col">Runs</th>
        </tr>
      </thead>
      <tbody>
        {#each activeDays as day (day.day)}
          <tr>
            <th scope="row">{longDay(day.day)}</th>
            <td>{formatDuration(day.saved)}</td>
            <td>{formatCount(day.failures)}</td>
            <td>{formatCount(day.runs)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</figure>

<style>
  .daily {
    margin: 0;
    padding: var(--space-2) var(--space-3) var(--space-1);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
  }

  .legend {
    display: flex;
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

  .saved {
    height: 180px;
  }

  .failures {
    height: 64px;
    border-top: 1px dashed var(--border);
  }

  .daily :global(.lc-axis-tick-label),
  .daily :global(text) {
    font-size: var(--text-xs);
    fill: var(--text-muted);
  }

  .daily :global(.lc-grid-line),
  .daily :global(.lc-grid line) {
    stroke: var(--chart-grid);
  }
</style>
