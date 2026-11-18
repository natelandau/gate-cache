<!--
  @component
  The panel around one homepage module: a section title, optional actions such as
  `MetricTabs` on the right, and the module's loading text, error `Notice`, and `EmptyState`.
  An error shows above the content, so data from an earlier load stays visible beside it.

  Props:
  - `title`: the section title, such as "Activity"
  - `subtitle`: optional muted text beside the title, such as "by time saved"
  - `titleId`: a page-unique id for the title, which labels the section
  - `noun`: optional name for the loading and error text, such as "top gates"; defaults to
    the lowercased title
  - `loading`: true to show loading text instead of the content; pass
    `query.loading && !query.data` to keep earlier data on screen while new data loads
  - `error`: the load error, if any
  - `empty`: true when there is nothing to show; no empty state shows beside an error
  - `emptyTitle`, `emptyDetail`: the empty state copy, from `src/lib/scope.ts`
  - `actions`: optional controls for the header
  - `footer`: optional links or footnotes pinned to the bottom of the card
  - `children`: the content
-->
<script lang="ts">
  import type { Snippet } from "svelte";
  import EmptyState from "./EmptyState.svelte";
  import Notice from "./Notice.svelte";
  import Skeleton from "./Skeleton.svelte";

  interface Props {
    title: string;
    subtitle?: string;
    titleId: string;
    noun?: string;
    loading: boolean;
    error?: Error;
    empty: boolean;
    emptyTitle: string;
    emptyDetail?: string;
    actions?: Snippet;
    footer?: Snippet;
    children: Snippet;
  }

  let {
    title,
    subtitle,
    titleId,
    noun,
    loading,
    error,
    empty,
    emptyTitle,
    emptyDetail,
    actions,
    footer,
    children,
  }: Props = $props();

  const subject = $derived(noun ?? title.toLowerCase());
</script>

<section class="module" aria-labelledby={titleId}>
  <header>
    <h2 id={titleId}>{title}</h2>
    {#if subtitle}<span class="subtitle">{subtitle}</span>{/if}
    {#if actions}<div class="actions">{@render actions()}</div>{/if}
  </header>
  {#if error}
    <Notice tone="error">Could not load {subject}: {error.message}</Notice>
  {/if}
  {#if loading}
    <p class="visually-hidden" aria-live="polite">Loading {subject}</p>
    <div class="skeletons">
      <Skeleton height={14} width="45%" />
      <Skeleton height={96} />
      <Skeleton height={14} width="70%" />
    </div>
  {:else if empty}
    {#if !error}<EmptyState title={emptyTitle} detail={emptyDetail} />{/if}
  {:else}
    {@render children()}
  {/if}
  {#if footer && !loading}<footer>{@render footer()}</footer>{/if}
</section>

<style>
  .module {
    display: flex;
    flex-direction: column;
    min-width: 0;
    padding: 18px 20px 20px;
    border-radius: var(--radius-card);
    background: var(--surface);
    box-shadow: var(--ring);
  }

  header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2) 10px;
    min-height: 28px;
    margin-bottom: 14px;
  }

  h2 {
    font-size: var(--text-md);
    font-weight: 500;
    letter-spacing: var(--track-lg);
  }

  .subtitle {
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    margin-left: auto;
  }

  .module > :global(.notice) {
    margin-bottom: var(--space-2);
  }

  .skeletons {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  footer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
    margin-top: auto;
    padding-top: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
</style>
