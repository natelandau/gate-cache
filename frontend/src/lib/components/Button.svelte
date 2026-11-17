<!--
  @component
  A command button sized like the other top bar and page controls.

  Props:
  - `onclick`: the action
  - `tone`: "default" | "accent"; accent draws attention to one control, such as new data
  - `square`: a square icon button; give it an `label`
  - `label`: accessible name, for buttons whose content is an icon
  - `title`: tooltip text
  - `disabled`: true while the action cannot run, such as during a load
  - `children`: the button content
-->
<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    onclick: () => void;
    tone?: "default" | "accent";
    square?: boolean;
    label?: string;
    title?: string;
    disabled?: boolean;
    children: Snippet;
  }

  let { onclick, tone = "default", square = false, label, title, disabled = false, children }: Props =
    $props();
</script>

<button type="button" class="button {tone}" class:square aria-label={label} {title} {disabled} {onclick}>
  {@render children()}
</button>

<style>
  .button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-1);
    flex: none;
    height: var(--control-height);
    padding: 0 var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    color: var(--text);
    font: inherit;
    font-size: var(--text-sm);
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
  }

  .button:hover:not(:disabled) {
    border-color: var(--border-strong);
    background: var(--surface-hover);
  }

  .button:disabled {
    color: var(--text-muted);
    cursor: progress;
  }

  .accent {
    border-color: transparent;
    background: var(--accent-soft);
    color: var(--accent);
  }

  .accent:hover:not(:disabled) {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .square {
    width: var(--control-height);
    padding: 0;
    color: var(--text-muted);
  }
</style>
