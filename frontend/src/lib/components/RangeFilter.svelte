<!--
  @component
  A segmented control for the date range presets. Built on native radio buttons, so arrow
  keys move between presets and Tab leaves the group.

  Props:
  - `value`: the selected range
  - `onchange`: called with the newly selected range
-->
<script lang="ts">
  import { RANGES, type Range } from "../state.svelte";

  interface Props {
    value: Range;
    onchange: (range: Range) => void;
  }

  let { value, onchange }: Props = $props();
  const uid = $props.id();
  const group = `range-${uid}`;
</script>

<fieldset class="range">
  <legend class="visually-hidden">Date range</legend>
  {#each RANGES as range (range.value)}
    <label title={range.long}>
      <input
        type="radio"
        name={group}
        value={range.value}
        checked={value === range.value}
        onchange={() => onchange(range.value)}
      />
      <span aria-hidden="true">{range.label}</span>
      <span class="visually-hidden">{range.long}</span>
    </label>
  {/each}
</fieldset>

<style>
  .range {
    display: inline-flex;
    margin: 0;
    padding: 2px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface-sunken);
    min-inline-size: auto;
  }

  label {
    position: relative;
    display: inline-flex;
  }

  input {
    position: absolute;
    inset: 0;
    margin: 0;
    opacity: 0;
    cursor: pointer;
  }

  span[aria-hidden] {
    display: inline-flex;
    align-items: center;
    height: calc(var(--control-height) - 6px);
    padding: 0 9px;
    border-radius: 3px;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  label:hover span[aria-hidden] {
    color: var(--text);
  }

  input:checked + span {
    background: var(--surface);
    color: var(--text);
    font-weight: 500;
    box-shadow: 0 0 0 1px var(--border);
  }

  input:focus-visible + span {
    outline: 2px solid var(--focus);
    outline-offset: 1px;
  }
</style>
