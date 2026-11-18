<!--
  @component
  A row of headline numbers separated by hairlines. Wraps on narrow screens.

  Props:
  - `stats`: the cells, each `{ label, value, hint?, title?, tone?, href?, delta? }`. `tone` "danger" or
    "flaky" colors a non-zero problem count; `href` turns the value into a link (for example to the
    Flaky page); `delta` adds a line with the change against the previous window, from
    `statDeltas` in `src/lib/deltas.ts`; `spark` adds a sparkline, from `summaryStats` in
    `src/lib/summary.ts`.
  - `deltaLabel`: optional text after each delta, such as "vs prev 30d"
  - `note`: optional footnote below the strip
  - `busy`: dims the values while newer numbers load
  - `highlight`: optional [from, to] day indexes the page is scoped to, kept bright on every
    sparkline
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
    delta?: { text: string; tone: "good" | "bad" | "neutral" };
    /** One value per day, null for a day with nothing to plot, and the line's color token. */
    spark?: { values: (number | null)[]; color: string };
  }
</script>

<script lang="ts">
  import { fly } from "svelte/transition";
  import { valueParts } from "../sparkline";
  import Icon from "./Icon.svelte";
  import Sparkline from "./Sparkline.svelte";

  interface Props {
    stats: Stat[];
    note?: string;
    deltaLabel?: string;
    busy?: boolean;
    highlight?: [from: number, to: number];
  }

  let { stats, note, deltaLabel, busy = false, highlight }: Props = $props();

  const reduced =
    typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

  /** Split "▲ 6%" into its direction and amount, so the arrow can be an icon. */
  function direction(text: string): { dir: "up" | "down" | null; amount: string } {
    if (text.startsWith("▲")) return { dir: "up", amount: text.slice(1).trim() };
    if (text.startsWith("▼")) return { dir: "down", amount: text.slice(1).trim() };
    return { dir: null, amount: text };
  }
</script>

<div class="strip-wrap" aria-busy={busy}>
  <dl class="strip" class:busy>
    {#each stats as stat (stat.label)}
      <div class="card" class:linked={!!stat.href}>
        <dt>
          <span>{stat.label}</span>
          {#if stat.title}<span class="info" title={stat.title}><Icon name="info" size={13} label={stat.title} /></span>{/if}
          {#if stat.href}<span class="go"><Icon name="arrow-up-right" size={14} /></span>{/if}
        </dt>
        <dd class="value" class:danger={stat.tone === "danger"} class:flaky={stat.tone === "flaky"}>
          {#key stat.value}
            <span class="swap" title={stat.value} in:fly={{ y: 3, duration: reduced ? 0 : 200 }}>
              {#if stat.href}
                <a href={stat.href}>{#each valueParts(stat.value) as part, i (i)}{#if part.unit}<span class="u">{part.text}</span>{:else}{part.text}{/if}{/each}</a>
              {:else}
                {#each valueParts(stat.value) as part, i (i)}{#if part.unit}<span class="u">{part.text}</span>{:else}{part.text}{/if}{/each}
              {/if}
            </span>
          {/key}
        </dd>
        {#if stat.delta}
          {@const d = direction(stat.delta.text)}
          <dd class="meta">
            <span class="delta {stat.delta.tone}">
              {#if d.dir}<Icon name={d.dir === "up" ? "trending-up" : "trending-down"} size={12} /><span
                  class="visually-hidden">{d.dir === "up" ? "Up" : "Down"}</span
                >{/if}{d.amount}
            </span>{#if deltaLabel}{" "}<span class="vs">{deltaLabel}</span>{/if}
          </dd>
        {/if}
        <dd class="hint" title={stat.hint} aria-hidden={stat.hint ? undefined : "true"}>{stat.hint ?? ""}</dd>
        {#if stat.spark}
          <dd class="spark-cell"><Sparkline values={stat.spark.values} color={stat.spark.color} {highlight} /></dd>
        {/if}
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

  .card {
    position: relative;
    display: flex;
    flex-direction: column;
    min-width: 0;
    padding: 14px var(--space-4) var(--space-3);
    border-radius: var(--radius-card);
    background: var(--surface);
    box-shadow: var(--ring);
    transition: box-shadow var(--dur-fast) var(--ease);
  }

  .card.linked:hover {
    box-shadow: var(--ring-hover);
  }

  dt {
    display: flex;
    align-items: center;
    gap: 5px;
    color: var(--text-muted);
    font-size: var(--text-sm);
    white-space: nowrap;
  }

  .info {
    display: inline-grid;
    color: var(--text-faint);
  }

  .go {
    display: inline-grid;
    margin-left: auto;
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

  .u {
    margin: 0 3px 0 1px;
    color: var(--text-muted);
    font-size: 0.6em;
    font-weight: 500;
    letter-spacing: 0;
  }

  .u:last-child {
    margin-right: 0;
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

  .delta {
    flex: none;
    display: inline-flex;
    align-items: center;
    gap: 3px;
    height: 20px;
    padding: 0 6px;
    border-radius: var(--radius-chip);
    background: var(--neutral-soft);
    color: var(--text-muted);
    font-weight: 500;
  }

  .delta.good {
    background: var(--ok-soft);
    color: var(--ok);
  }

  .delta.bad {
    background: var(--danger-soft);
    color: var(--danger);
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
    margin-top: auto;
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
