<!--
  @component
  A top bar control: a button that shows the current value and opens a popover of choices.
  Opening moves focus to the popover's first control, or the checked radio of a group. Escape
  and a click outside close the popover and return focus to the button when focus was inside
  it; Escape in a text or date field, or one a control inside already handled, stays with it. Tabbing out of the popover closes it.

  Props:
  - `caption`: what the control sets, such as "Date range"; read before the label by screen
    readers and used as the popover's name
  - `label`: the current value, shown on the button
  - `title`: tooltip text for the button
  - `width`: the popover width, such as "380px"; left out, the popover shrink-wraps its content
  - `open`: whether the popover is open; bind it to open the popover from outside
  - `onopen`: called each time the popover opens
  - `icon`: the button icon, 16px, drawn with `currentColor`
  - `children`: the popover content; receives a `close` function that closes the popover and
    focuses the button
-->
<script lang="ts">
  import { type Snippet, tick, untrack } from "svelte";
  import { popoverShift } from "../popoverShift";
  import Icon from "./Icon.svelte";

  interface Props {
    caption: string;
    label: string;
    title?: string;
    width?: string;
    open?: boolean;
    onopen?: () => void;
    icon: Snippet;
    children: Snippet<[close: () => void]>;
  }

  let { caption, label, title, width, open = $bindable(false), onopen, icon, children }: Props = $props();

  const uid = $props.id();
  const TEXT_FIELD = "input:not([type='checkbox'], [type='radio']), select, textarea";
  let root: HTMLElement;
  let button: HTMLButtonElement;
  let popover: HTMLElement;
  let shift = $state(0);

  const FIRST_CONTROL =
    "input:not([type='radio']), input[type='radio']:checked, button, select, textarea, [tabindex]:not([tabindex='-1'])";

  function place() {
    const gutter = parseFloat(getComputedStyle(popover).getPropertyValue("--space-4"));
    shift = popoverShift(
      root.getBoundingClientRect().left,
      popover.offsetWidth,
      document.documentElement.clientWidth,
      gutter,
    );
  }

  $effect(() => {
    if (!open) return;
    untrack(() => onopen?.());
    void tick().then(() => {
      place();
      popover.querySelector<HTMLElement>(FIRST_CONTROL)?.focus();
    });
  });

  function close() {
    open = false;
    button.focus();
  }

  function dismiss() {
    const focusInside = root.contains(document.activeElement) && document.activeElement !== button;
    open = false;
    if (focusInside) button.focus();
  }

  // Content that changes the popover's width, such as a picker replacing a list, needs a new shift.
  $effect(() => {
    if (!open) return;
    const observer = new ResizeObserver(place);
    observer.observe(popover);
    return () => observer.disconnect();
  });

  $effect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!root.contains(event.target as Node)) dismiss();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
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
    onclick={() => (open = !open)}
  >
    {@render icon()}
    <span class="visually-hidden">{caption}:</span>
    <span class="label">{label}</span>
    <span class="caret"><Icon name="chevron-down" size={14} /></span>
  </button>
  <div class="popover" class:fit={!width} bind:this={popover} id="{uid}-popover" role="dialog" aria-label={caption} hidden={!open} style:width style:translate={shift ? `${shift}px` : undefined}>
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
    padding: 0 var(--space-2) 0 10px;
    border: 0;
    border-radius: var(--radius-control);
    background: var(--surface);
    box-shadow: var(--ring);
    color: var(--text);
    font: inherit;
    font-size: var(--text-sm);
    cursor: pointer;
    transition: box-shadow var(--dur-fast) var(--ease);
  }

  .control:hover {
    box-shadow: var(--ring-hover);
  }

  .control.open {
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
    display: grid;
    color: var(--text-faint);
  }

  .popover {
    position: absolute;
    top: calc(100% + var(--space-1));
    left: 0;
    z-index: 10;
    max-width: calc(100vw - 2 * var(--space-4));
    padding: var(--space-2);
    border-radius: var(--radius-popover);
    background: var(--surface);
    box-shadow: var(--shadow-popover);
    animation: fade-in var(--dur-fast) var(--ease-in);
  }

  .popover.fit {
    width: max-content;
  }

  .popover[hidden] {
    display: none;
  }
</style>
