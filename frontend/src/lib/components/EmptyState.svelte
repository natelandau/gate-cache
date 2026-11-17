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

  interface Props {
    title: string;
    detail?: string;
    children?: Snippet;
  }

  let { title, detail, children }: Props = $props();
</script>

<div class="empty">
  <p class="title">{title}</p>
  {#if detail}<p class="detail">{detail}</p>{/if}
  {#if children}<div class="extra">{@render children()}</div>{/if}
</div>

<style>
  .empty {
    padding: var(--space-5) var(--space-4);
    text-align: center;
    color: var(--text-muted);
  }

  p {
    margin: 0;
  }

  .title {
    color: var(--text);
    font-weight: 500;
  }

  .detail {
    margin-top: var(--space-1);
    font-size: var(--text-sm);
  }

  .extra {
    margin-top: var(--space-3);
  }
</style>
