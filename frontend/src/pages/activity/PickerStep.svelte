<!--
  @component
  One picker of the Filter menu that picks from a loaded list: any number of values, such as
  gates, or one value with `single`, such as a Breakdown row. Apply with nothing checked removes
  a multi-value filter.

  Props:
  - `label`: names the list
  - `load`: fetches the choices; reruns when the global filters or `key` change
  - `key`: the inputs of `load` beyond the global filters
  - `checked`: the values already applied, picked at first; a single picker starts on the first
    choice when none is applied
  - `single`: pick one value from a select instead of checking any number
  - `onapply`: called with the picked choices' items
-->
<script lang="ts" generics="T">
  import Button from "../../lib/components/Button.svelte";
  import CheckList from "../../lib/components/CheckList.svelte";
  import Notice from "../../lib/components/Notice.svelte";
  import Select from "../../lib/components/Select.svelte";
  import type { ListChoice } from "../../lib/filtermenu";
  import { createQuery } from "../../lib/query.svelte";
  import { ACTIVITY_FILTERS } from "../../lib/terms";

  interface Props {
    label: string;
    load: (signal: AbortSignal) => Promise<ListChoice<T>[]>;
    key: () => unknown;
    checked: string[];
    single?: boolean;
    onapply: (items: T[]) => void;
  }

  let { label, load, key, checked, single = false, onapply }: Props = $props();

  const query = createQuery((signal) => load(signal), () => key());
  let draft = $state<string[] | undefined>();
  const choices = $derived(query.data ?? []);
  const values = $derived(draft ?? (single && !checked.length ? choices.slice(0, 1).map((c) => c.value) : checked));
  const items = $derived(choices.filter((choice) => values.includes(choice.value)).map((choice) => choice.item));
</script>

{#if query.error}
  <Notice tone="error">Could not load the choices: {query.error.message}</Notice>
{:else if !query.data}
  <p class="note" aria-live="polite">Loading choices</p>
{:else if choices.length === 0}
  <p class="note">Nothing to pick in this range.</p>
{:else if single}
  <div class="row">
    <Select {label} value={values[0] ?? ""} options={choices} onchange={(next) => (draft = [next])} />
    <Button tone="accent" disabled={!items.length} onclick={() => onapply(items)}>{ACTIVITY_FILTERS.apply}</Button>
  </div>
{:else}
  <CheckList {label} options={choices} checked={values} onchange={(next) => (draft = next)} />
  <div class="actions">
    <Button tone="accent" onclick={() => onapply(items)}>{ACTIVITY_FILTERS.apply}</Button>
  </div>
{/if}

<style>
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
  }

  .row :global(select) {
    max-width: 100%;
  }

  .row :global(label) {
    min-width: 0;
    max-width: 100%;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
  }

  .note {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
</style>
