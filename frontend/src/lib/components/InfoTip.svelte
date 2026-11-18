<!--
  @component
  Explains a label, either through an info icon after it or through the label itself. The
  explanation opens on hover, on keyboard focus, and on click or tap, and Escape closes it.
  Screen readers read it as the control's description.

  The bubble is placed against the window when it opens, so a scrolling table never clips it,
  and it opens leftward near the window's right edge.

  Props:
  - `text`: the explanation
  - `label`: accessible name of the info icon (default "More information")
  - `children`: optional label shown before the icon, such as a headline card label
  - `trigger`: optional label that opens the tip on its own, with no icon, such as a sortable
    column header. It receives the tooltip's id; point the control's `aria-describedby` at it,
    and focus on that control opens the tip
-->
<script lang="ts">
  import type { Snippet } from "svelte";
  import Icon from "./Icon.svelte";
  import TooltipSurface from "./TooltipSurface.svelte";

  interface Props {
    text: string;
    label?: string;
    children?: Snippet;
    trigger?: Snippet<[string]>;
  }

  let { text, label = "More information", children, trigger }: Props = $props();

  const uid = $props.id();
  const tipId = `${uid}-tip`;
  // TooltipSurface max-width plus a margin from the window edge.
  const BUBBLE_ROOM = 300;
  const GAP = 6;

  let pinned = $state(false);
  // Escape hides the bubble even while hover or focus would show it, until the pointer or focus leaves.
  let dismissed = $state(false);
  let position = $state({ top: 0, left: 0 });
  let root: HTMLElement | undefined = $state();
  let bubble: HTMLElement | undefined = $state();

  // Measure where the tip is each time it opens, so a scrolled table or a resized window never
  // leaves the bubble in a stale spot.
  function place(): void {
    if (!root) return;
    const box = root.getBoundingClientRect();
    const left = box.left + BUBBLE_ROOM > window.innerWidth ? box.right - BUBBLE_ROOM + 20 : box.left - 8;
    // Open upward when the bubble would run past the bottom of the window.
    const height = bubble?.offsetHeight ?? 0;
    const below = box.bottom + GAP;
    const top = below + height > window.innerHeight - 8 ? box.top - GAP - height : below;
    position = { top: Math.max(8, top), left: Math.max(8, left) };
  }

  // The bubble is fixed to the window, so an open one follows its label when anything scrolls.
  function follow(): void {
    if (root && (pinned || root.matches(":hover, :has(:focus-visible)"))) place();
  }

  $effect(() => {
    const options = { capture: true, passive: true };
    window.addEventListener("scroll", follow, options);
    window.addEventListener("resize", follow, options);
    return () => {
      window.removeEventListener("scroll", follow, options);
      window.removeEventListener("resize", follow, options);
    };
  });

  function reset(): void {
    pinned = false;
    dismissed = false;
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<span
  bind:this={root}
  class="tip"
  class:pinned
  class:dismissed
  class:labeled={!!children}
  onpointerenter={place}
  onfocusin={place}
  onpointerleave={() => (dismissed = false)}
  onfocusout={reset}
  onkeydown={(event) => {
    if (event.key === "Escape") {
      pinned = false;
      dismissed = true;
    }
  }}
>
  {#if trigger}
    {@render trigger(tipId)}
  {:else}
    {@render children?.()}
    <button
      type="button"
      aria-label={label}
      aria-describedby={tipId}
      aria-expanded={pinned}
      onclick={() => {
        pinned = !pinned;
        dismissed = false;
      }}
    >
      <Icon name="info" size={13} />
    </button>
  {/if}
  <span class="bubble" bind:this={bubble} role="tooltip" id={tipId} style:top="{position.top}px" style:left="{position.left}px"
    ><TooltipSurface {text} /></span
  >
</span>

<style>
  .tip {
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

  /* Fixed to the window, so an ancestor that scrolls or clips never cuts it off. TooltipSurface owns
     how it looks. */
  .bubble {
    position: fixed;
    z-index: 30;
    opacity: 0;
    transform: translateY(2px);
    pointer-events: none;
    transition:
      opacity var(--dur-fast) var(--ease),
      transform var(--dur-fast) var(--ease);
  }

  .tip:hover .bubble,
  .tip:has(:focus-visible) .bubble,
  .pinned .bubble {
    opacity: 1;
    transform: none;
  }

  .tip.dismissed .bubble {
    opacity: 0;
  }
</style>
