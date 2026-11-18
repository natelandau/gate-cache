<!--
  @component
  An info icon that explains a label. The explanation opens on hover, on keyboard focus, and on
  click or tap, and Escape closes it. Screen readers read it as the button's description. Pass
  the label itself as `children` and hovering anywhere on the label opens it too.

  Props:
  - `text`: the explanation
  - `label`: accessible name of the button (default "More information")
  - `children`: optional label shown before the icon, such as a headline card label
  - `trigger`: optional label that opens the tip on its own, with no icon, such as a sortable
    column header. It receives the tooltip's id; point the control's `aria-describedby` at it,
    and focus on that control opens the tip
-->
<script lang="ts">
  import type { Snippet } from "svelte";
  import Icon from "./Icon.svelte";
  import Tooltip from "./Tooltip.svelte";

  interface Props {
    text: string;
    label?: string;
    children?: Snippet;
    trigger?: Snippet<[string]>;
  }

  let { text, label = "More information", children, trigger }: Props = $props();

  const uid = $props.id();
  let pinned = $state(false);
  // Escape hides the bubble even while hover or focus would show it, until the pointer or focus leaves.
  let dismissed = $state(false);
  let flip = $state(false);
  let root: HTMLElement | undefined = $state();

  // Tooltip's max-width plus the bubble's 8px offset and a margin.
  const BUBBLE_ROOM = 300;

  // Near the right edge of the window, open the bubble leftward so it stays on screen. Measured
  // when the tip mounts and when the window resizes, so hovering the label needs no handler.
  function place(): void {
    if (root) flip = root.getBoundingClientRect().left + BUBBLE_ROOM > window.innerWidth;
  }

  $effect(place);
</script>

<svelte:window onresize={place} />

{#if trigger}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <span
    class="tip bare"
    class:flip
    class:dismissed
    bind:this={root}
    onpointerleave={() => (dismissed = false)}
    onfocusout={() => (dismissed = false)}
    onkeydown={(event) => {
      if (event.key === "Escape") dismissed = true;
    }}
  >
    <span class="hint">{@render trigger(`${uid}-tip`)}</span>
    <span class="bubble"><Tooltip {text} role="tooltip" id="{uid}-tip" /></span>
  </span>
{:else}
<span class="tip" class:pinned class:flip class:dismissed class:labeled={!!children} bind:this={root}>
  {#if children}{@render children()}{/if}
  <button
    type="button"
    aria-label={label}
    aria-describedby="{uid}-tip"
    aria-expanded={pinned}
    onpointerleave={() => (dismissed = false)}
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
  <span class="bubble"><Tooltip {text} role="tooltip" id="{uid}-tip" /></span>
</span>
{/if}

<style>
  .tip {
    position: relative;
    display: inline-flex;
    align-items: center;
  }

  .labeled {
    gap: 4px;
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

  /* Anchors the shared Tooltip under the icon; Tooltip owns how it looks. */
  .bubble {
    position: absolute;
    top: calc(100% + 6px);
    left: -8px;
    z-index: 20;
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

  .hint {
    display: inline-flex;
    align-items: center;
  }

  .bare:focus-within .bubble,
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
