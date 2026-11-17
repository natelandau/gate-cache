<!--
  @component
  A labeled native select sized like the other page controls.

  Props:
  - `label`: the visible label text, which also names the select
  - `value`: the selected option's value
  - `options`: the choices, in order, as `{ value, label }`
  - `onchange`: called with the newly selected value
-->
<script lang="ts">
  interface Props {
    label: string;
    value: string;
    options: { value: string; label: string }[];
    onchange: (value: string) => void;
  }

  let { label, value, options, onchange }: Props = $props();
</script>

<label class="field">
  <span>{label}</span>
  <select {value} onchange={(event) => onchange(event.currentTarget.value)}>
    {#each options as option (option.value)}
      <option value={option.value}>{option.label}</option>
    {/each}
  </select>
</label>

<style>
  .field {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  select {
    height: var(--control-height);
    padding: 0 var(--space-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    color: var(--text);
    font: inherit;
    font-size: var(--text-sm);
    cursor: pointer;
  }

  select:hover {
    border-color: var(--border-strong);
    background: var(--surface-hover);
  }
</style>
