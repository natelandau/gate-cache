<!--
  @component
  A small inline label, such as an outcome or a "flaky" marker. Status tones are for outcomes
  and problems only; use `neutral` for anything else.

  Props:
  - `tone`: "neutral" | "accent" | "ok" | "warn" | "danger" | "info" | "flaky"
    (default "neutral")
  - `title`: optional hover text that explains the label
  - `children`: the label text
-->
<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    tone?: "neutral" | "accent" | "ok" | "warn" | "danger" | "info" | "flaky";
    title?: string;
    children: Snippet;
  }

  let { tone = "neutral", title, children }: Props = $props();
</script>

<span class="badge {tone}" {title}>{@render children()}</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    height: 20px;
    padding: 0 6px;
    border-radius: var(--radius-chip);
    font-size: var(--text-xs);
    font-weight: 500;
    line-height: 1;
    letter-spacing: 0;
    white-space: nowrap;
    /* As tall as a line of text, so top alignment centers it in table rows. */
    vertical-align: top;
  }

  .neutral {
    background: var(--neutral-soft);
    color: var(--text-muted);
  }

  .accent {
    background: var(--accent-soft);
    color: var(--accent);
  }

  .ok {
    background: var(--ok-soft);
    color: var(--ok);
  }

  .warn {
    background: var(--warn-soft);
    color: var(--warn);
  }

  .danger {
    background: var(--danger-soft);
    color: var(--danger);
  }

  .info {
    background: var(--info-soft);
    color: var(--info);
  }

  .flaky {
    background: var(--flaky-soft);
    color: var(--flaky);
  }
</style>
