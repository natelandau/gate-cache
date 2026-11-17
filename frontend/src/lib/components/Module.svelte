<!--
  @component
  The panel around one homepage module: a section title, optional actions such as
  `MetricTabs` on the right, and the module's loading text, error `Notice`, and `EmptyState`.
  An error shows above the content, so data from an earlier load stays visible beside it.

  Props:
  - `title`: the section title, such as "Activity"
  - `titleId`: a page-unique id for the title, which labels the section
  - `noun`: optional name for the loading and error text, such as "top gates"; defaults to
    the lowercased title
  - `loading`: true to show loading text instead of the content; pass
    `query.loading && !query.data` to keep earlier data on screen while new data loads
  - `error`: the load error, if any
  - `empty`: true when there is nothing to show; no empty state shows beside an error
  - `emptyTitle`, `emptyDetail`: the empty state copy, from `src/lib/scope.ts`
  - `actions`: optional controls for the header
  - `children`: the content
-->
<script lang="ts">
  import type { Snippet } from "svelte";
  import EmptyState from "./EmptyState.svelte";
  import Notice from "./Notice.svelte";

  interface Props {
    title: string;
    titleId: string;
    noun?: string;
    loading: boolean;
    error?: Error;
    empty: boolean;
    emptyTitle: string;
    emptyDetail?: string;
    actions?: Snippet;
    children: Snippet;
  }

  let {
    title,
    titleId,
    noun,
    loading,
    error,
    empty,
    emptyTitle,
    emptyDetail,
    actions,
    children,
  }: Props = $props();

  const subject = $derived(noun ?? title.toLowerCase());
</script>

<section class="module" aria-labelledby={titleId}>
  <header>
    <h2 id={titleId} class="section-title">{title}</h2>
    {#if actions}<div class="actions">{@render actions()}</div>{/if}
  </header>
  {#if error}
    <Notice tone="error">Could not load {subject}: {error.message}</Notice>
  {/if}
  {#if loading}
    <p class="loading" aria-live="polite">Loading {subject}</p>
  {:else if empty}
    {#if !error}<EmptyState title={emptyTitle} detail={emptyDetail} />{/if}
  {:else}
    {@render children()}
  {/if}
</section>

<style>
  .module {
    min-width: 0;
    padding: var(--space-3) 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
  }

  header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    min-height: 24px;
    margin-bottom: 10px;
  }

  header .section-title {
    margin: 0;
  }

  .actions {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-left: auto;
  }

  .module > :global(.notice) {
    margin-bottom: var(--space-2);
  }

  .loading {
    margin: 0;
    color: var(--text-muted);
  }
</style>
