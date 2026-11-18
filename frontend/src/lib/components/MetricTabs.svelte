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
    gap: 2px;
    padding: 2px;
    border: 0;
    border-radius: var(--radius-control);
    background: var(--surface-sunken);
    box-shadow: inset 0 0 0 1px var(--border);
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
    display: inline-flex;
    align-items: center;
    height: 24px;
    padding: 0 9px;
    border-radius: 4px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    transition:
      background-color var(--dur-fast) var(--ease),
      color var(--dur-fast) var(--ease),
      box-shadow var(--dur-fast) var(--ease);
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
    box-shadow: var(--ring);
  }
</style>
