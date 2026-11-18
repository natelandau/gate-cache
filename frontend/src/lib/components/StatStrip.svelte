<!--
  @component
  A row of headline numbers separated by hairlines. Wraps on narrow screens.

  Props:
  - `stats`: the cells, each `{ label, value, hint?, title?, tone?, href?, delta?, spark? }`. `tone` "danger" or
    "flaky" colors a non-zero problem count; `href` turns the value into a link (for example to the
    Flaky page); `delta` adds a line with the change against the previous window, from
    `statDeltas` in `src/lib/deltas.ts`; `spark` adds a sparkline, from `summaryStats` in
    `src/lib/summary.ts`.
  - `deltaLabel`: optional text after each delta, such as "vs prev 30d"
  - `note`: optional footnote below the strip
  - `busy`: dims the values while newer numbers load
  - `highlight`: optional [from, to] day indexes the page is scoped to, kept bright on every
    sparkline
  - `placeholders`: when set and `stats` is empty, that many skeleton cards show while the
    numbers load
-->
<script lang="ts" module>
  export interface Stat {
    label: string;
    value: string;
    /** Secondary text under the value, such as a count the value excludes. */
    hint?: string;
    /** How the value is computed, shown as a tooltip on the label. */
    title?: string;
    tone?: "default" | "danger" | "flaky";
    href?: string;
    /** Change against the previous window; its arrow and text carry the meaning, not the tone. */
    delta?: { text: string; tone: "good" | "bad" | "neutral"; dir: "up" | "down" | null };
    /** One value per day, null for a day with nothing to plot, and the line's CSS color. */
    spark?: { values: (number | null)[]; color: string };
  }
</script>

<script lang="ts">
  import { fly } from "svelte/transition";
  import { prefersReducedMotion } from "../motion";
  import Icon from "./Icon.svelte";
  import InfoTip from "./InfoTip.svelte";
  import Skeleton from "./Skeleton.svelte";
  import Sparkline from "./Sparkline.svelte";
  import TrendBadge from "./TrendBadge.svelte";
  import UnitValue from "./UnitValue.svelte";

  interface Props {
    stats: Stat[];
    note?: string;
    deltaLabel?: string;
    busy?: boolean;
    highlight?: [from: number, to: number];
    placeholders?: number;
  }

  let { stats, note, deltaLabel, busy = false, highlight, placeholders }: Props = $props();

  const reduced = prefersReducedMotion();

</script>

<div class="strip-wrap" aria-busy={busy}>
  <dl class="strip" class:busy>
    {#if stats.length === 0 && placeholders}
      {#each { length: placeholders }, i (i)}
        <div class="card placeholder">
          <Skeleton height={12} width="60%" />
          <Skeleton height={28} width="75%" />
          <Skeleton height={12} width="85%" />
        </div>
      {/each}
    {/if}
    {#each stats as stat (stat.label)}
      <div class="card" class:linked={!!stat.href}>
        <dt>
          <span>{stat.label}</span>{#if stat.title}<InfoTip text={stat.title} label="About {stat.label}" />{/if}
          {#if stat.href}<span class="go"><Icon name="arrow-up-right" size={14} /></span>{/if}
        </dt>
        <dd class="value" class:danger={stat.tone === "danger"} class:flaky={stat.tone === "flaky"}>
          {#key stat.value}
            <span class="swap" title={stat.value} in:fly={{ y: 3, duration: reduced ? 0 : 200 }}>
              {#if stat.href}
                <a href={stat.href}><UnitValue value={stat.value} /></a>
              {:else}
                <UnitValue value={stat.value} />
              {/if}
            </span>
          {/key}
        </dd>
        <!-- Every card renders all five rows, so the subgrid lines them up across cards. -->
        <dd class="meta" aria-hidden={stat.delta ? undefined : "true"}>
          {#if stat.delta}
            <TrendBadge dir={stat.delta.dir} text={stat.delta.text} tone={stat.delta.tone} />{#if deltaLabel}<span
                class="vs">{deltaLabel}</span
              >{/if}
          {/if}
        </dd>
        <dd class="hint" title={stat.hint} aria-hidden={stat.hint ? undefined : "true"}>{stat.hint ?? ""}</dd>
        <dd class="spark-cell" aria-hidden={stat.spark ? undefined : "true"}>
          {#if stat.spark}<Sparkline values={stat.spark.values} color={stat.spark.color} {highlight} />{/if}
        </dd>
      </div>
    {/each}
  </dl>
  {#if note}<p class="note"><Icon name="info" size={13} />{note}</p>{/if}
</div>

<style>
  .strip {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: var(--space-3);
    margin: 0;
  }

  /* Each card spans five rows of the strip and shares them through subgrid, so a label that
     wraps to two lines pushes every card's value down together. */
  .card {
    position: relative;
    display: grid;
    grid-row: span 5;
    grid-template-rows: subgrid;
    row-gap: 0;
    min-width: 0;
    padding: 14px var(--space-4) var(--space-3);
    border-radius: var(--radius-card);
    background: var(--surface);
    box-shadow: var(--ring);
    transition: box-shadow var(--dur-fast) var(--ease);
  }

  .card.placeholder {
    display: flex;
    flex-direction: column;
    grid-row: auto;
    gap: 10px;
  }

  .card.linked:hover {
    box-shadow: var(--ring-hover);
  }

  dt {
    color: var(--text-muted);
    font-size: var(--text-sm);
    line-height: 18px;
  }

  /* Room for the arrow that a linked card shows on hover. */
  .linked dt {
    padding-right: 14px;
  }

  dt :global(.tip) {
    margin-left: 4px;
    vertical-align: -3px;
  }

  .go {
    position: absolute;
    top: 14px;
    right: var(--space-3);
    display: inline-grid;
    color: var(--text-faint);
    opacity: 0;
    transition: opacity var(--dur-fast) var(--ease);
  }

  .card.linked:hover .go {
    opacity: 1;
  }

  dd {
    margin: 0;
    min-width: 0;
  }

  .value {
    margin: var(--space-2) 0;
    font-size: var(--text-kpi);
    font-weight: 600;
    line-height: 32px;
    letter-spacing: var(--track-kpi);
    white-space: nowrap;
  }

  .swap {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .value a {
    color: inherit;
    text-decoration: none;
  }

  /* The value's link covers the whole card, so the card is one click target. */
  .value a::after {
    content: "";
    position: absolute;
    inset: 0;
    border-radius: var(--radius-card);
  }

  .value a:focus-visible {
    outline: none;
  }

  .value a:focus-visible::after {
    outline: 2px solid var(--focus);
    outline-offset: 1px;
  }

  .danger {
    color: var(--danger);
  }

  .flaky {
    color: var(--flaky);
  }

  .meta {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }

  .vs {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .hint {
    min-height: 16px;
    margin-top: var(--space-1);
    overflow: hidden;
    color: var(--text-muted);
    font-size: var(--text-xs);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .spark-cell {
    align-self: end;
    padding-top: 10px;
  }

  .busy .value,
  .busy .meta {
    opacity: 0.55;
  }

  .note {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: var(--space-2) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
