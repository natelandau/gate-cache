<!--
  @component
  A list of checkboxes for picking any number of values, such as the outcomes of a filter. A
  long list gets a search box that narrows the list by label; checked values stay checked when
  the search hides them.

  Props:
  - `label`: names the list for screen readers and the search box
  - `options`: the choices, in order, as `{ value, label }`
  - `checked`: the checked values
  - `onchange`: called with the checked values, in option order
  - `searchAt`: the option count from which the search box shows (default 8)
-->
<script lang="ts">
  interface Props {
    label: string;
    options: { value: string; label: string }[];
    checked: string[];
    onchange: (values: string[]) => void;
    searchAt?: number;
  }

  let { label, options, checked, onchange, searchAt = 8 }: Props = $props();

  let search = $state("");
  const needle = $derived(search.trim().toLocaleLowerCase());
  const shown = $derived(
    needle ? options.filter((option) => option.label.toLocaleLowerCase().includes(needle)) : options,
  );

  function set(value: string, on: boolean): void {
    const next = new Set(checked);
    if (on) next.add(value);
    else next.delete(value);
    onchange(options.map((option) => option.value).filter((v) => next.has(v)));
  }
</script>

<fieldset class="list">
  <legend class="visually-hidden">{label}</legend>
  {#if options.length >= searchAt}
    <input class="search" type="search" placeholder="Search" aria-label="Search {label}" bind:value={search} />
  {/if}
  <div class="options">
    {#each shown as option (option.value)}
      <label class="option" title={option.label}>
        <input
          type="checkbox"
          checked={checked.includes(option.value)}
          onchange={(event) => set(option.value, event.currentTarget.checked)}
        />
        <span>{option.label}</span>
      </label>
    {:else}
      <p class="none">No match.</p>
    {/each}
  </div>
</fieldset>

<style>
  .list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
    margin: 0;
    padding: 0;
    border: 0;
  }

  /* Zero base width, stretched by min-width, so the box never widens a shrink-wrapped popover. */
  .search {
    width: 0;
    min-width: 100%;
    height: var(--control-height);
    padding: 0 var(--space-2);
    border: 0;
    border-radius: var(--radius-control);
    background: var(--surface-sunken);
    box-shadow: var(--ring);
    color: var(--text);
    font: inherit;
    font-size: var(--text-sm);
  }

  .search::placeholder {
    color: var(--text-faint);
  }

  .options {
    display: flex;
    flex-direction: column;
    max-height: 280px;
    overflow-y: auto;
  }

  .option {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: var(--row-height);
    padding: 0 var(--space-2);
    border-radius: var(--radius-control);
    color: var(--text);
    font-size: var(--text-sm);
    cursor: pointer;
  }

  .option:hover {
    background: var(--surface-hover);
  }

  .option span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  input[type="checkbox"] {
    flex: none;
    margin: 0;
    accent-color: var(--accent);
  }

  .none {
    margin: 0;
    padding: var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
</style>
