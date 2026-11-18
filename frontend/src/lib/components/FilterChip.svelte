<!--
  @component
  A removable chip that names one page-local filter, such as an Activity reason or the days
  the Overview is scoped to. Long labels are cut with an ellipsis; `title` carries the full text.

  Props:
  - `label`: the visible text, such as "Reason: dirty tree"
  - `title`: optional hover text, such as the full reason
  - `removeLabel`: accessible name and tooltip of the remove button
  - `onremove`: called when the remove button is pressed
-->
<script lang="ts">
  import Badge from "./Badge.svelte";
  import Button from "./Button.svelte";

  interface Props {
    label: string;
    title?: string;
    removeLabel: string;
    onremove: () => void;
  }

  let { label, title, removeLabel, onremove }: Props = $props();
</script>

<span class="chip">
  <Badge title={title ?? label}><span class="text">{label}</span></Badge>
  <Button square label={removeLabel} title={removeLabel} onclick={onremove}>×</Button>
</span>

<style>
  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    min-width: 0;
    max-width: 100%;
  }

  .text {
    max-width: 48ch;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
