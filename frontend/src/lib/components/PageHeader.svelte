<!--
  @component
  The heading row of a page: the title, a muted line naming what the page shows, and the page's
  filter chips.

  Props:
  - `title`: the page title
  - `headingId`: a page-unique id for the `h1`, which labels the page's section
  - `subtitle`: optional line under the title, such as the repo filter and the date span
  - `heading`: bindable `h1` element, so a page can move focus to it
  - `children`: optional chips, such as a `FilterChip` for a page-local filter
-->
<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    title: string;
    headingId: string;
    subtitle?: string;
    heading?: HTMLElement;
    children?: Snippet;
  }

  let { title, headingId, subtitle, heading = $bindable(), children }: Props = $props();
</script>

<div class="head">
  <div class="titles">
    <h1 id={headingId} tabindex="-1" bind:this={heading}>{title}</h1>
    {#if subtitle}<p class="subtitle">{subtitle}</p>{/if}
  </div>
  {#if children}<div class="chips">{@render children()}</div>{/if}
</div>

<style>
  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-3) var(--space-4);
  }

  .titles {
    min-width: 0;
  }

  h1 {
    font-size: var(--text-h1);
    font-weight: 600;
    letter-spacing: var(--track-h1);
    line-height: 28px;
  }

  h1:focus {
    outline: none;
  }

  .subtitle {
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
</style>
