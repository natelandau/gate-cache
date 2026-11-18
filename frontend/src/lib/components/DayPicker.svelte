<!--
  @component
  The keyboard and pointer overlay that makes a daily bar chart's days pickable. It sits over
  the plot as one listbox with an option per day, outlines the picked days, and washes out the
  rest. The chart's frame forwards pointer input to `pick`.

  Props:
  - `pick`: the chart's day picking, from `createDayPick`
  - `days`: the chart's days, in order
  - `label`: the accessible name of one day, with its values
-->
<script lang="ts" generics="T extends { day: string }">
  import { bandInset } from "../daily";
  import type { DayPick } from "../daypick.svelte";

  interface Props {
    pick: DayPick;
    days: T[];
    label: (day: T) => string;
  }

  let { pick, days, label }: Props = $props();

  const uid = $props.id();
  const inset = $derived(bandInset(days.length, pick.bandPadding));
</script>

<div
  class="picker"
  role="listbox"
  aria-multiselectable="true"
  aria-label="Pick days to scope the page"
  aria-describedby="{uid}-help"
  aria-activedescendant={days.length ? `${uid}-${pick.nav.cursor.at}` : undefined}
  tabindex="0"
  bind:this={pick.listbox}
  style:top="{pick.padding.top}px"
  style:bottom="{pick.padding.bottom}px"
  style:left="{pick.padding.left}px"
  style:right="{pick.padding.right}px"
  onkeydown={(event) => pick.nav.key(event)}
>
  <div class="columns" style:margin-inline="{inset}%">
    {#each days as day, index (day.day)}
      {@const on = pick.shown !== null && index >= pick.shown[0] && index <= pick.shown[1]}
      <span
        id="{uid}-{index}"
        role="option"
        aria-selected={on}
        aria-label={label(day)}
        class="column"
        class:selected={on}
        class:dimmed={pick.shown !== null && !on}
        class:cursor={index === pick.nav.cursor.at}
      ></span>
    {/each}
    {#if pick.shown}
      <span
        class="range"
        aria-hidden="true"
        style:left="{(pick.shown[0] / days.length) * 100}%"
        style:width="{((pick.shown[1] - pick.shown[0] + 1) / days.length) * 100}%"
      ></span>
    {/if}
  </div>
</div>
<p id="{uid}-help" class="visually-hidden">
  Arrow keys move between days. Enter or Space picks a day, Shift with an arrow key extends
  the pick, and Escape clears it.
</p>

<style>
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
</style>
