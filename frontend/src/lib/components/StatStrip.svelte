<!--
  @component
  A row of headline numbers separated by hairlines. Wraps on narrow screens.

  Props:
  - `stats`: the cells, each `{ label, value, hint?, tone?, href?, delta? }`. `tone` "danger" or
    "flaky" colors a non-zero problem count; `href` turns the value into a link (for example to the
    Flaky page); `delta` adds a line with the change against the previous window, from
    `statDeltas` in `src/lib/deltas.ts`.
  - `deltaLabel`: optional text after each delta, such as "vs prev 30d"
  - `note`: optional footnote below the strip
  - `busy`: dims the values while newer numbers load
-->
<script lang="ts" module>
  export interface Stat {
    label: string;
    value: string;
    /** Secondary text under the value, such as a count the value excludes. */
    hint?: string;
    tone?: "default" | "danger" | "flaky";
    href?: string;
    /** Change against the previous window; its arrow and text carry the meaning, not the tone. */
    delta?: { text: string; tone: "good" | "bad" | "neutral" };
  }
</script>

<script lang="ts">
  interface Props {
    stats: Stat[];
    note?: string;
    deltaLabel?: string;
    busy?: boolean;
  }

  let { stats, note, deltaLabel, busy = false }: Props = $props();
</script>

<div class="strip-wrap" aria-busy={busy}>
  <dl class="strip" class:busy>
    {#each stats as stat (stat.label)}
      <div class="cell">
        <dt>{stat.label}</dt>
        <dd class:danger={stat.tone === "danger"} class:flaky={stat.tone === "flaky"}>
          {#if stat.href}
            <a href={stat.href}>{stat.value}</a>
          {:else}
            {stat.value}
          {/if}
        </dd>
        {#if stat.hint}<dd class="hint">{stat.hint}</dd>{/if}
        {#if stat.delta}
          <dd class="delta {stat.delta.tone}">
            {stat.delta.text}{#if deltaLabel}{" "}<span class="vs">{deltaLabel}</span>{/if}
          </dd>
        {/if}
      </div>
    {/each}
  </dl>
  {#if note}<p class="note">{note}</p>{/if}
</div>

<style>
  .strip {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
    margin: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    overflow: hidden;
  }

  .cell {
    padding: var(--space-2) var(--space-3);
    border-left: 1px solid var(--border);
    margin-left: -1px;
    min-width: 0;
  }

  dt {
    font-size: var(--text-xs);
    color: var(--text-muted);
    white-space: nowrap;
  }

  dd {
    margin: 2px 0 0;
    font-size: var(--text-xl);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  dd a {
    color: inherit;
    text-decoration-color: var(--border-strong);
    text-underline-offset: 3px;
  }

  dd a:hover {
    text-decoration-color: currentColor;
  }

  .danger {
    color: var(--danger);
  }

  .flaky {
    color: var(--flaky);
  }

  .hint {
    margin-top: 0;
    font-size: var(--text-xs);
    font-weight: 400;
    color: var(--text-muted);
  }

  .delta {
    margin-top: 2px;
    font-size: var(--text-sm);
    font-weight: 400;
    color: var(--text-faint);
  }

  .delta.good {
    color: var(--ok);
  }

  .delta.bad {
    color: var(--danger);
  }

  .vs {
    color: var(--text-faint);
  }

  .busy dd {
    opacity: 0.55;
  }

  .note {
    margin: var(--space-1) 0 0;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }
</style>
