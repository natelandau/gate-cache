<!--
  @component
  A top bar control: a button that shows the current value and opens a popover of choices.
  Opening moves focus to the popover's first control, or the checked radio of a group. Escape
  and a click outside close the popover and return focus to the button when focus was inside
  it; Escape in a text or date field stays with the field. Tabbing out of the popover closes it.

  Props:
  - `caption`: what the control sets, such as "Date range"; read before the label by screen
    readers and used as the popover's name
  - `label`: the current value, shown on the button
  - `title`: tooltip text for the button
  - `width`: the popover width, such as "380px"
  - `onopen`: called each time the popover opens
  - `icon`: the button icon, 16px, drawn with `currentColor`
  - `children`: the popover content; receives a `close` function that closes the popover and
    focuses the button
-->
<script lang="ts">
  import { type Snippet, tick } from "svelte";

  interface Props {
    caption: string;
    label: string;
    title?: string;
    width: string;
    onopen?: () => void;
    icon: Snippet;
    children: Snippet<[close: () => void]>;
  }

  let { caption, label, title, width, onopen, icon, children }: Props = $props();

  const uid = $props.id();
  const TEXT_FIELD = "input:not([type='checkbox'], [type='radio']), select, textarea";
  let open = $state(false);
  let root: HTMLElement;
  let button: HTMLButtonElement;
  let popover: HTMLElement;

  const FIRST_CONTROL =
    "input:not([type='radio']), input[type='radio']:checked, button, select, textarea, [tabindex]:not([tabindex='-1'])";

  async function toggle() {
    open = !open;
    if (!open) return;
    onopen?.();
    await tick();
    popover.querySelector<HTMLElement>(FIRST_CONTROL)?.focus();
  }

  function close() {
    open = false;
    button.focus();
  }

  function dismiss() {
    const focusInside = root.contains(document.activeElement) && document.activeElement !== button;
    open = false;
    if (focusInside) button.focus();
  }

  $effect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!root.contains(event.target as Node)) dismiss();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      // Escape in a text or date field belongs to the field, such as closing a date picker.
      const target = event.target;
      if (target instanceof Element && target.closest(TEXT_FIELD)) return;
      // Keeps an open gate panel from closing on the same key press.
      event.preventDefault();
      close();
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  });
</script>

<div
  class="dropdown"
  bind:this={root}
  onfocusout={(event) => {
    const next = event.relatedTarget;
    if (open && next instanceof Node && !root.contains(next)) open = false;
  }}
>
  <button
    type="button"
    class="control"
    class:open
    bind:this={button}
    aria-expanded={open}
    aria-controls="{uid}-popover"
    {title}
    onclick={toggle}
  >
    {@render icon()}
    <span class="visually-hidden">{caption}:</span>
    <span class="label">{label}</span>
    <svg class="caret" viewBox="0 0 10 10" width="10" height="10" aria-hidden="true" fill="currentColor">
      <path d="M1.5 3.5h7L5 7.5z" />
    </svg>
  </button>
  <div class="popover" bind:this={popover} id="{uid}-popover" role="dialog" aria-label={caption} hidden={!open} style:width>
    {@render children(close)}
  </div>
</div>

<style>
  .dropdown {
    position: relative;
    min-width: 0;
  }

  .control {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    max-width: 260px;
    height: var(--control-height);
    padding: 0 var(--space-3);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--surface);
    color: var(--text);
    font: inherit;
    font-size: var(--text-sm);
    cursor: pointer;
  }

  .control:hover {
    background: var(--surface-hover);
  }

  .control.open {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
  }

  .control :global(svg) {
    flex: none;
    color: var(--text-muted);
  }

  .label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .caret {
    color: var(--text-faint);
  }

  .popover {
    position: absolute;
    top: calc(100% + var(--space-1));
    left: 0;
    z-index: 10;
    max-width: calc(100vw - 2 * var(--space-4));
    padding: var(--space-2);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-popover);
    background: var(--surface);
    box-shadow: var(--shadow-popover);
  }

  .popover[hidden] {
    display: none;
  }
</style>
