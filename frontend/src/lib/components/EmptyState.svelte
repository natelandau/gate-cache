<!--
  @component
  A quiet placeholder for a region with nothing to show.

  Props:
  - `title`: one short sentence, such as "No runs in this range"
  - `detail`: optional hint for what to do next
  - `children`: optional actions or extra markup below the detail
-->
<script lang="ts">
  import type { Snippet } from "svelte";
  import Icon from "./Icon.svelte";

  interface Props {
    title: string;
    detail?: string;
    children?: Snippet;
  }

  let { title, detail, children }: Props = $props();
</script>

<div class="empty">
  <span class="tile"><Icon name="inbox" size={18} /></span>
  <p class="title">{title}</p>
  {#if detail}<p class="detail">{detail}</p>{/if}
  {#if children}<div class="extra">{@render children()}</div>{/if}
</div>

<style>
  .empty {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-1);
    padding: var(--space-5) var(--space-4);
    text-align: center;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  p {
    margin: 0;
    max-width: 52ch;
  }

  .tile {
    display: grid;
    place-items: center;
    width: 36px;
    height: 36px;
    margin-bottom: var(--space-1);
    border-radius: var(--radius-card);
    background: var(--surface-sunken);
    box-shadow: inset 0 0 0 1px var(--border);
    color: var(--text-faint);
  }

  .title {
    color: var(--text);
    font-size: var(--text-md);
    font-weight: 500;
  }

  .extra {
    margin-top: var(--space-2);
  }
</style>
