<!--
  @component
  A removable chip that names one page-local filter, such as an Activity reason or the days
  the Overview is scoped to. Long labels are cut with an ellipsis; `title` carries the full text.

  Props:
  - `label`: the visible text, such as "Reason: dirty tree"
  - `title`: optional hover text, such as the full reason
  - `removeLabel`: accessible name and tooltip of the remove button
  - `onremove`: called when the remove button is pressed
  - `onedit`: when given, the label is a button that calls it, such as to reopen the filter's
    picker
  - `editLabel`: accessible name of the label button, such as "Edit the outcome filter"
-->
<script lang="ts">
  import Icon from "./Icon.svelte";

  interface Props {
    label: string;
    title?: string;
    removeLabel: string;
    onremove: () => void;
    onedit?: () => void;
    editLabel?: string;
  }

  let { label, title, removeLabel, onremove, onedit, editLabel }: Props = $props();
</script>

<span class="chip" title={title ?? label}>
  {#if onedit}
    <button type="button" class="text edit" aria-label={editLabel ? `${editLabel}: ${label}` : undefined} onclick={onedit}>
      {label}
    </button>
  {:else}
    <span class="text">{label}</span>
  {/if}
  <button type="button" class="remove" aria-label={removeLabel} title={removeLabel} onclick={onremove}>
    <Icon name="x" size={14} />
  </button>
</span>

<style>
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    height: 26px;
    min-width: 0;
    max-width: 100%;
    padding: 0 3px 0 9px;
    border-radius: var(--radius-chip);
    background: var(--accent-soft);
    color: var(--accent);
    font-size: var(--text-sm);
    font-weight: 500;
    animation: fade-in var(--dur-med) var(--ease-in);
  }

  .text {
    max-width: 48ch;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .edit {
    padding: 0;
    border: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  .edit:hover {
    text-decoration: underline;
  }

  .remove {
    display: grid;
    place-items: center;
    width: 20px;
    height: 20px;
    padding: 0;
    border: 0;
    border-radius: 3px;
    background: transparent;
    color: inherit;
    cursor: pointer;
    transition: background-color var(--dur-fast) var(--ease);
  }

  .remove:hover {
    background: var(--border);
  }
</style>
