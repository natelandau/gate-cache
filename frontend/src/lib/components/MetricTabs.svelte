<!--
  @component
  A small segmented control that picks what a module measures, such as Runs or Time saved.
  It is a native radio group, so arrow keys move between options and Tab leaves the group.

  Props:
  - `label`: the group's name for screen readers, such as "Activity metric"
  - `options`: the choices, in display order
  - `value`: the selected option's value
  - `onchange`: called with the newly selected value
-->
<script lang="ts">
  interface Props {
    label: string;
    options: { value: string; label: string }[];
    value: string;
    onchange: (v: string) => void;
  }

  let { label, options, value, onchange }: Props = $props();

  const uid = $props.id();
</script>

<fieldset class="tabs">
  <legend class="visually-hidden">{label}</legend>
  {#each options as option (option.value)}
    <label>
      <input
        type="radio"
        name="{uid}-metric"
        value={option.value}
        checked={value === option.value}
        onchange={() => onchange(option.value)}
      />
      <span>{option.label}</span>
    </label>
  {/each}
</fieldset>

<style>
  .tabs {
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
    display: flex;
  }

  input {
    position: absolute;
    inset: 0;
    margin: 0;
    opacity: 0;
    cursor: pointer;
  }

  span {
    padding: 1px var(--space-2);
    border-radius: 3px;
    color: var(--text-muted);
    font-size: var(--text-sm);
    white-space: nowrap;
  }

  label:hover span {
    color: var(--text);
  }

  input:focus-visible + span {
    outline: 2px solid var(--focus);
    outline-offset: 1px;
  }

  input:checked + span {
    background: var(--surface);
    color: var(--text);
    font-weight: 500;
    box-shadow: 0 0 0 1px var(--border);
  }
</style>
