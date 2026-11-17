<!--
  @component
  The date range picker: a button that shows the range and opens a popover with three tabs.
  Relative holds the rolling presets, Calendar the calendar periods, and Custom two dates and an
  Apply button. Tabs, presets, and periods are native radio groups, so arrow keys move inside a
  group and Tab leaves it. A preset or period applies at once; custom dates apply on Apply.

  Props:
  - `value`: the selected range
  - `onchange`: called with the newly selected range
-->
<script lang="ts" module>
  import type { Preset, RangeSpec } from "../range";

  /** Return the range a preset choice selects. */
  export function presetSpec(preset: Preset): RangeSpec {
    return { kind: "preset", preset };
  }
</script>

<script lang="ts">
  import { isValidCustom, localDay, PERIODS, PRESETS, rangeLabel, resolveRange } from "../range";
  import Dropdown from "./Dropdown.svelte";

  interface Props {
    value: RangeSpec;
    onchange: (range: RangeSpec) => void;
  }

  let { value, onchange }: Props = $props();

  type Tab = "relative" | "calendar" | "custom";
  const TABS: { value: Tab; label: string }[] = [
    { value: "relative", label: "Relative" },
    { value: "calendar", label: "Calendar" },
    { value: "custom", label: "Custom" },
  ];
  const TAB_OF: Record<RangeSpec["kind"], Tab> = { preset: "relative", period: "calendar", custom: "custom" };

  const uid = $props.id();
  let now = $state(new Date());
  // Bumped on each open so the tab and custom dates drop unapplied edits.
  let opens = $state(0);
  const today = $derived(localDay(now));
  let tab = $derived.by(() => {
    void opens;
    return TAB_OF[value.kind];
  });

  // The custom dates start as the current range, so switching to Custom shows what is selected.
  const initial = $derived.by(() => {
    void opens;
    if (value.kind === "custom") return { start: value.start, end: value.end };
    const { from } = resolveRange(value, now);
    return { start: from === undefined ? "" : localDay(new Date(from * 1000)), end: today };
  });
  let start = $derived(initial.start);
  let end = $derived(initial.end);
  const valid = $derived(isValidCustom(start, end, today));
</script>

<Dropdown caption="Date range" label={rangeLabel(value)} width="380px" onopen={() => {
    now = new Date();
    opens += 1;
  }}>
  {#snippet icon()}
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <rect x="2" y="3" width="12" height="11" rx="1.5" />
      <path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" />
    </svg>
  {/snippet}
  {#snippet children(close)}
    <fieldset class="tabs">
      <legend class="visually-hidden">Range type</legend>
      {#each TABS as option (option.value)}
        <label>
          <input
            type="radio"
            name="{uid}-tab"
            value={option.value}
            checked={tab === option.value}
            onchange={() => (tab = option.value)}
          />
          <span>{option.label}</span>
        </label>
      {/each}
    </fieldset>

    {#if tab === "relative"}
      <fieldset class="choices presets">
        <legend class="visually-hidden">Relative range</legend>
        {#each PRESETS as preset (preset.value)}
          <label title={preset.long}>
            <input
              type="radio"
              name="{uid}-preset"
              value={preset.value}
              checked={value.kind === "preset" && value.preset === preset.value}
              onchange={() => onchange(presetSpec(preset.value))}
            />
            <span aria-hidden="true">{preset.label}</span>
            <span class="visually-hidden">{preset.long}</span>
          </label>
        {/each}
      </fieldset>
    {:else if tab === "calendar"}
      <fieldset class="choices periods">
        <legend class="visually-hidden">Calendar period</legend>
        {#each PERIODS as period (period.value)}
          <label>
            <input
              type="radio"
              name="{uid}-period"
              value={period.value}
              checked={value.kind === "period" && value.period === period.value}
              onchange={() => onchange({ kind: "period", period: period.value })}
            />
            <span>{period.label}</span>
          </label>
        {/each}
      </fieldset>
    {:else}
      <form
        class="custom"
        onsubmit={(event) => {
          event.preventDefault();
          if (!valid) return;
          onchange({ kind: "custom", start, end });
          close();
        }}
      >
        <label>
          <span class="visually-hidden">Start date</span>
          <input type="date" value={start} max={today} oninput={(event) => (start = event.currentTarget.value)} />
        </label>
        <span class="to">to</span>
        <label>
          <span class="visually-hidden">End date, inclusive</span>
          <input type="date" value={end} max={today} oninput={(event) => (end = event.currentTarget.value)} />
        </label>
        <button type="submit" disabled={!valid}>Apply</button>
      </form>
    {/if}
  {/snippet}
</Dropdown>

<style>
  fieldset {
    margin: 0;
    padding: 0;
    border: 0;
    min-inline-size: auto;
  }

  label {
    position: relative;
    display: flex;
  }

  input[type="radio"] {
    position: absolute;
    inset: 0;
    margin: 0;
    opacity: 0;
    cursor: pointer;
  }

  input[type="radio"]:focus-visible + span {
    outline: 2px solid var(--focus);
    outline-offset: 1px;
  }

  .tabs {
    display: flex;
    padding: 2px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface-sunken);
  }

  .tabs label {
    flex: 1;
  }

  .tabs span {
    flex: 1;
    padding: 3px var(--space-3);
    border-radius: 3px;
    color: var(--text-muted);
    font-size: var(--text-sm);
    text-align: center;
  }

  .tabs label:hover span {
    color: var(--text);
  }

  .tabs input:checked + span {
    background: var(--surface);
    color: var(--text);
    font-weight: 500;
    box-shadow: 0 0 0 1px var(--border);
  }

  .choices {
    display: grid;
    gap: 6px;
    margin-top: var(--space-2);
  }

  .presets {
    grid-template-columns: repeat(6, 1fr);
  }

  .periods {
    grid-template-columns: repeat(2, 1fr);
  }

  .choices span[aria-hidden],
  .periods span {
    flex: 1;
    padding: 5px var(--space-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface-sunken);
    color: var(--text);
    font-size: var(--text-sm);
  }

  .presets span[aria-hidden] {
    text-align: center;
  }

  .presets label:hover span[aria-hidden],
  .periods label:hover span {
    border-color: var(--border-strong);
  }

  .choices input:checked + span {
    border-color: var(--accent);
    background: var(--accent);
    color: var(--accent-text);
    font-weight: 500;
  }

  .custom {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }

  .custom input,
  .custom button {
    height: var(--control-height);
    border-radius: var(--radius);
    font: inherit;
    font-size: var(--text-sm);
  }

  .custom input {
    padding: 0 6px;
    border: 1px solid var(--border-strong);
    background: var(--surface);
    color: var(--text);
  }

  .to {
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  .custom button {
    padding: 0 var(--space-3);
    border: 0;
    background: var(--accent);
    color: var(--accent-text);
    font-weight: 500;
    cursor: pointer;
  }

  .custom button:disabled {
    background: var(--surface-sunken);
    color: var(--text-muted);
    box-shadow: inset 0 0 0 1px var(--border);
    cursor: not-allowed;
  }
</style>
