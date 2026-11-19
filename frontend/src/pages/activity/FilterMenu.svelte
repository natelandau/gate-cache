<!--
  @component
  The Activity page's Filter menu. It lists every filter a link can apply, in sections. Flaky
  trees and Spot checks are checkboxes that apply at once; each other entry opens its own
  picker inside the menu, filled in with the applied values. Escape in a picker goes back to
  the list, and Escape in the list closes the menu.

  Props:
  - `filter`: the page-local filters from the hash route
  - `onchange`: called with the new filter

  Methods:
  - `edit(kind)`: opens the menu at the picker of one filter, such as from its chip
-->
<script lang="ts">
  import { tick } from "svelte";
  import { getBreakdown, getGates, getReasons, spanScope, type ActivityFilter } from "../../lib/api";
  import { filterParts } from "../../lib/activity";
  import Button from "../../lib/components/Button.svelte";
  import Dropdown from "../../lib/components/Dropdown.svelte";
  import Icon from "../../lib/components/Icon.svelte";
  import Select from "../../lib/components/Select.svelte";
  import { DIMENSIONS, type Dimension } from "../../lib/dimensions";
  import {
    gateChoices,
    groupChoices,
    listValues,
    MENU_SECTIONS,
    outcomeChoices,
    pickerEntry,
    reasonChoices,
    withList,
    withToggle,
    type FilterKind,
    type MenuEntry,
    type ToggleKind,
  } from "../../lib/filtermenu";
  import { rangeDays, spanFromInputs } from "../../lib/selection";
  import { filters } from "../../lib/state.svelte";
  import { ACTIVITY_FILTERS } from "../../lib/terms";
  import PickerStep from "./PickerStep.svelte";

  interface Props {
    filter: ActivityFilter;
    onchange: (filter: ActivityFilter) => void;
  }

  let { filter, onchange }: Props = $props();

  let menuOpen = $state(false);
  let step = $state<MenuEntry | null>(null);
  let panel: HTMLElement | undefined = $state();
  // The picker `edit` asks for, opened when the menu opens instead of the list.
  let pending: MenuEntry | null = null;
  // Lists follow the picked days, so they hold only values that can match runs.
  const scope = () => spanScope(filter.span);

  // Each single-value picker's draft, set from the applied filter when the picker opens.
  let by = $state<Dimension>("branch");
  let from = $state("");
  let to = $state("");
  // The days the global range allows, read when the picker opens.
  let bounds = $state<{ min?: string; max: string }>({ max: "" });
  const picked = $derived(spanFromInputs(from, to, bounds.min, bounds.max));

  const dimensionOptions = DIMENSIONS.map((d) => ({ value: d.value, label: d.label }));
  const applied = $derived(new Map(filterParts(filter).map((part) => [part.key, part.value])));

  function open(entry: MenuEntry): void {
    if (entry.kind === "group") by = filter.group?.by ?? "branch";
    if (entry.kind === "span") {
      from = filter.span?.from ?? "";
      to = filter.span?.to ?? "";
      bounds = rangeDays(filters.range, new Date());
    }
    step = entry;
  }

  async function focusStep(): Promise<void> {
    await tick();
    const body = panel?.querySelector<HTMLElement>(".body input, .body select, .body button");
    (body ?? panel?.querySelector<HTMLElement>("button"))?.focus();
  }

  export async function edit(kind: FilterKind): Promise<void> {
    const entry = pickerEntry(kind);
    if (!entry) return;
    pending = entry;
    menuOpen = true;
    await tick();
    pending = null;
    open(entry);
    await focusStep();
  }

  function apply(next: ActivityFilter, close: () => void): void {
    onchange(next);
    close();
  }

  function applySpan(close: () => void): void {
    if (picked) apply({ ...filter, span: picked }, close);
  }

  function toggle(kind: ToggleKind, on: boolean): void {
    onchange(withToggle(filter, kind, on));
  }

  async function back(): Promise<void> {
    const kind = step?.kind;
    step = null;
    await tick();
    panel?.querySelector<HTMLElement>(`[data-kind="${kind}"] button`)?.focus();
  }

  // Escape in a picker steps back to the list; the menu then closes on the next Escape.
  $effect(() => {
    const node = panel;
    if (!node) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || step === null) return;
      event.preventDefault();
      void back();
    };
    node.addEventListener("keydown", onKey);
    return () => node.removeEventListener("keydown", onKey);
  });
</script>

<Dropdown
  bind:open={menuOpen}
  caption={ACTIVITY_FILTERS.caption}
  label={ACTIVITY_FILTERS.button}
  onopen={() => (step = pending)}
>
  {#snippet icon()}
    <Icon name="list-filter" />
  {/snippet}
  {#snippet children(close)}
    <div class="panel" class:picker={step !== null} bind:this={panel}>
      {#if step === null}
        {#each MENU_SECTIONS as section (section.title)}
          <section class="section" role="group" aria-labelledby="filter-section-{section.title}">
            <h3 id="filter-section-{section.title}">{section.title}</h3>
            <ul class="entries">
              {#each section.entries as entry (entry.kind)}
                <li data-kind={entry.kind}>
                  {#if section.toggles}
                    <label class="toggle">
                      <input
                        type="checkbox"
                        checked={filter[entry.kind] === true}
                        onchange={(event) => toggle(entry.kind as ToggleKind, event.currentTarget.checked)}
                      />
                      {entry.label}
                    </label>
                  {:else}
                    <button type="button" class="entry" onclick={() => { open(entry); void focusStep(); }}>
                      <span>{entry.label}</span>
                      {#if applied.get(entry.kind)}<span class="applied">{applied.get(entry.kind)}</span>{/if}
                      <Icon name="chevron-right" />
                    </button>
                  {/if}
                </li>
              {/each}
            </ul>
          </section>
        {/each}
      {:else}
        <div class="head">
          <Button onclick={back} label="{ACTIVITY_FILTERS.back}: all filters" square>
            <Icon name="chevron-left" />
          </Button>
          <span class="title">{step.label}</span>
        </div>
        <div class="body">
          {#if step.kind === "outcome"}
            <PickerStep
              label={ACTIVITY_FILTERS.outcome}
              load={async () => outcomeChoices()}
              key={() => null}
              checked={listValues(filter, "outcome")}
              onapply={(items) => apply(withList(filter, "outcome", items), close)}
            />
          {:else if step.kind === "gate"}
            <PickerStep
              label={ACTIVITY_FILTERS.gate}
              load={async (signal) => gateChoices(await getGates({ signal, scope: scope() }), filter.gate)}
              key={() => filter.span}
              checked={listValues(filter, "gate")}
              onapply={(items) => apply(withList(filter, "gate", items), close)}
            />
          {:else if step.kind === "reason"}
            <PickerStep
              label={ACTIVITY_FILTERS.reason}
              load={async (signal) => reasonChoices(await getReasons({ signal, scope: scope() }), filter.reason)}
              key={() => filter.span}
              checked={listValues(filter, "reason")}
              onapply={(items) => apply(withList(filter, "reason", items), close)}
            />
          {:else if step.kind === "group"}
            <div class="fields">
              <Select label="Group by" value={by} options={dimensionOptions} onchange={(value) => (by = value as Dimension)} />
              {#key by}
                <PickerStep
                  label="Value"
                  single
                  load={async (signal) =>
                    groupChoices(by, (await getBreakdown(by, { signal, scope: scope() })).rows, filter.group)}
                  key={() => [by, filter.span]}
                  checked={filter.group?.by === by ? [filter.group.key] : []}
                  onapply={([group]) => group && apply({ ...filter, group }, close)}
                />
              {/key}
            </div>
          {:else if step.kind === "span"}
            <div class="fields">
              <label class="date">
                <span>From</span>
                <input type="date" bind:value={from} min={bounds.min} max={bounds.max} required />
              </label>
              <label class="date">
                <span>To</span>
                <input type="date" bind:value={to} min={from || bounds.min} max={bounds.max} placeholder={from} />
              </label>
              <Button tone="accent" disabled={!picked} onclick={() => applySpan(close)}>{ACTIVITY_FILTERS.apply}</Button>
            </div>
          {/if}
        </div>
      {/if}
    </div>
  {/snippet}
</Dropdown>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 0;
  }

  .panel.picker {
    min-width: var(--picker-min-width);
  }

  .section {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .section + .section {
    padding-top: var(--space-3);
    border-top: 1px solid var(--border);
  }

  h3 {
    margin: 0;
    padding: 0 var(--space-2);
    color: var(--text);
    font-size: var(--text-sm);
    font-weight: 600;
  }

  .entries {
    display: grid;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .entry,
  .toggle {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    min-height: var(--row-height);
    padding: 0 var(--space-2) 0 var(--space-5);
    border: 0;
    border-radius: var(--radius-control);
    background: transparent;
    color: var(--text);
    font: inherit;
    font-size: var(--text-sm);
    text-align: left;
    cursor: pointer;
  }

  .entry:hover,
  .toggle:hover {
    background: var(--surface-hover);
  }

  .entry span:first-child {
    flex: 1 0 auto;
  }

  .applied {
    min-width: 0;
    overflow: hidden;
    color: var(--text-muted);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .toggle input {
    margin: 0;
    accent-color: var(--accent);
  }

  .head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .title {
    font-size: var(--text-md);
    font-weight: 500;
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 0;
  }

  .fields {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2) var(--space-3);
  }

  .date {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  .date input {
    height: var(--control-height);
    padding: 0 6px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-control);
    background: var(--surface);
    color: var(--text);
    font: inherit;
    font-size: var(--text-sm);
  }
</style>
