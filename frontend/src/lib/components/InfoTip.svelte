<!--
  @component
  An info icon that explains a label. The explanation opens on hover, on keyboard focus, and on
  click or tap, and Escape closes it. Screen readers read it as the button's description.

  Props:
  - `text`: the explanation
  - `label`: accessible name of the button (default "More information")
-->
<script lang="ts">
  import Icon from "./Icon.svelte";

  interface Props {
    text: string;
    label?: string;
  }

  let { text, label = "More information" }: Props = $props();

  const uid = $props.id();
  let pinned = $state(false);
  // Escape hides the bubble even while hover or focus would show it, until the pointer or focus leaves.
  let dismissed = $state(false);
  let flip = $state(false);
  let root: HTMLElement | undefined = $state();

  // Matches the bubble's max-width plus its offset and a margin, in the styles below.
  const BUBBLE_ROOM = 280;

  // Near the right edge of the window, open the bubble leftward so it stays on screen.
  function place(): void {
    if (root) flip = root.getBoundingClientRect().left + BUBBLE_ROOM > window.innerWidth;
  }
</script>

<span class="tip" class:pinned class:flip class:dismissed bind:this={root}>
  <button
    type="button"
    aria-label={label}
    aria-describedby="{uid}-tip"
    aria-expanded={pinned}
    onpointerenter={place}
    onpointerleave={() => (dismissed = false)}
    onfocus={place}
    onclick={() => {
      pinned = !pinned;
      dismissed = false;
    }}
    onblur={() => {
      pinned = false;
      dismissed = false;
    }}
    onkeydown={(event) => {
      if (event.key === "Escape") {
        pinned = false;
        dismissed = true;
      }
    }}
  >
    <Icon name="info" size={13} />
  </button>
  <span class="bubble" role="tooltip" id="{uid}-tip">{text}</span>
</span>

<style>
  .tip {
    position: relative;
    display: inline-flex;
  }

  button {
    display: grid;
    place-items: center;
    width: 16px;
    height: 16px;
    padding: 0;
    border: 0;
    border-radius: 50%;
    background: none;
    color: var(--text-faint);
    cursor: help;
    transition: color var(--dur-fast) var(--ease);
  }

  button:hover,
  .pinned button {
    color: var(--text);
  }

  .bubble {
    position: absolute;
    top: calc(100% + 6px);
    left: -8px;
    z-index: 20;
    width: max-content;
    /* With the 8px offset and a margin, BUBBLE_ROOM in the script reserves this width. */
    max-width: 260px;
    padding: var(--space-2) 10px;
    border-radius: var(--radius-popover);
    background: var(--surface);
    box-shadow: var(--shadow-popover);
    color: var(--text);
    font-size: var(--text-xs);
    font-weight: 400;
    line-height: 16px;
    white-space: normal;
    opacity: 0;
    transform: translateY(2px);
    pointer-events: none;
    transition:
      opacity var(--dur-fast) var(--ease),
      transform var(--dur-fast) var(--ease);
  }

  .flip .bubble {
    left: auto;
    right: -8px;
  }

  .tip:hover .bubble,
  button:focus-visible + .bubble,
  .pinned .bubble {
    opacity: 1;
    transform: none;
  }

  .tip.dismissed .bubble {
    opacity: 0;
  }
</style>
