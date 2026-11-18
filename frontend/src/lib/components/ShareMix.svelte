<!--
  @component
  The share of each part of a whole as one stacked bar, with a legend that lists every part,
  its count, and its percent. The legend is the text equivalent, so only the bar is hidden from
  screen readers.

  Props:
  - `parts`: the parts in display order, each `{ key, label, count, color, title?, href? }`;
    pass a nonzero total. A part with `href` and a count links its count and bar segment.
  - `format`: how a count reads in the legend and bar titles; defaults to a plain number
  - `noun`: what a linked count counts, for its accessible name; defaults to "runs"
-->
<script lang="ts">
  import { formatCount } from "../format";
  import { type MixPart, partShares } from "../rank";

  interface Props {
    parts: MixPart[];
    format?: (count: number) => string;
    noun?: string;
  }

  let { parts, format = formatCount, noun = "runs" }: Props = $props();

  const shares = $derived(partShares(parts, (part) => part.count));
</script>

<figure class="mix">
  <div class="bar" aria-hidden="true">
    {#each shares as item (item.part.key)}
      {#if item.count > 0}
        <!-- The legend links are the keyboard and screen-reader path, so segments skip the tab order. -->
        <svelte:element
          this={item.part.href ? "a" : "span"}
          class="segment"
          href={item.part.href}
          tabindex={item.part.href ? -1 : undefined}
          style:background={item.part.color}
          style:width="{item.share * 100}%"
          title="{item.part.label}: {format(item.count)} ({item.percent})"
        ></svelte:element>
      {/if}
    {/each}
  </div>
  <ul class="legend">
    {#each shares as item (item.part.key)}
      <li title={item.part.title}>
        <i class="swatch" style:background={item.part.color}></i>
        <span>{item.part.label}</span>
        {#if item.part.href && item.count > 0}
          <a
            class="num"
            href={item.part.href}
            aria-label="{format(item.count)} {item.part.label} {noun}. Open in Activity"
            >{format(item.count)}</a
          >
        {:else}
          <span class="num">{format(item.count)}</span>
        {/if}
        <span class="num percent">{item.percent}</span>
      </li>
    {/each}
  </ul>
</figure>

<style>
  .mix {
    margin: 0;
  }

  .bar {
    display: flex;
    gap: 2px;
    height: 10px;
    overflow: hidden;
    border-radius: 3px;
    background: var(--track);
  }

  .segment {
    display: block;
    height: 100%;
    flex-shrink: 1;
    min-width: 2px;
    transition: width var(--dur-slow) var(--ease);
  }

  a.num {
    color: inherit;
    text-decoration: none;
  }

  a.num:hover {
    color: var(--accent);
    text-decoration: underline;
  }

  .legend {
    display: grid;
    grid-template-columns: 10px minmax(0, 1fr) auto 44px;
    column-gap: 10px;
    align-items: center;
    margin: 14px 0 0;
    padding: 0;
    font-size: var(--text-sm);
    list-style: none;
  }

  li {
    display: grid;
    grid-column: 1 / -1;
    grid-template-columns: subgrid;
    align-items: center;
    height: 32px;
    border-bottom: 1px solid var(--border-row);
  }

  li:last-child {
    border-bottom: 0;
  }

  .swatch {
    width: 10px;
    height: 10px;
    border-radius: 2px;
  }

  .num {
    font-weight: 500;
    text-align: right;
  }

  .percent {
    color: var(--text-muted);
    font-weight: 400;
  }
</style>
