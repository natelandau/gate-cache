<!--
  @component
  The live/stale indicator in the top bar.

  Shows `Live · updated 2s ago` while polls succeed, `Stale · last update 1m ago` once polls
  keep failing, and `Ingest failing` when the server reports a background ingest error.
  Screen readers hear only state changes, not the ticking time.

  Props:
  - `stale`: true after repeated failed polls
  - `updatedAt`: Unix seconds of the last successful poll, or null before the first
  - `now`: the current Unix seconds, from a ticking clock
  - `ingestError`: the server's latest ingest failure, or null
  - `lastIngest`: Unix seconds when new events last arrived, or null
-->
<script lang="ts">
  import { formatRelative, formatTimestamp } from "../format";

  interface Props {
    stale: boolean;
    updatedAt: number | null;
    now: number;
    ingestError: string | null;
    lastIngest: number | null;
  }

  let { stale, updatedAt, now, ingestError, lastIngest }: Props = $props();

  const status = $derived.by((): "connecting" | "live" | "stale" | "error" => {
    if (stale) return "stale";
    if (updatedAt === null) return "connecting";
    return ingestError ? "error" : "live";
  });

  const label = $derived(
    { connecting: "Connecting", live: "Live", stale: "Stale", error: "Ingest failing" }[status],
  );

  const age = $derived.by(() => {
    if (status === "connecting") return "";
    if (updatedAt === null) return "no response";
    const ago = formatRelative(updatedAt, now);
    return status === "stale" ? `last update ${ago}` : `updated ${ago}`;
  });

  const title = $derived(
    [
      ingestError ? `Ingest error: ${ingestError}` : null,
      lastIngest === null ? "No events ingested yet" : `New events last ingested ${formatTimestamp(lastIngest)}`,
    ]
      .filter(Boolean)
      .join("\n"),
  );
</script>

<div class="freshness {status}" {title}>
  <span class="dot" aria-hidden="true"></span>
  <span class="label">{label}</span>
  {#if age}<span class="age" aria-hidden="true">· {age}</span>{/if}
  <span class="visually-hidden" role="status">
    {label}{ingestError ? `: ${ingestError}` : ""}
  </span>
</div>

<style>
  .freshness {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: var(--control-height);
    font-size: var(--text-sm);
    color: var(--text-muted);
    white-space: nowrap;
  }

  .label {
    color: var(--text-muted);
  }

  .dot {
    position: relative;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--text-faint);
  }

  .live .dot {
    background: var(--palette-500);
  }

  .live .dot::after {
    content: "";
    position: absolute;
    inset: 0;
    border-radius: 50%;
    background: var(--palette-500);
    animation: pulse 2.4s var(--ease-in) infinite;
  }

  .stale .dot {
    background: var(--palette-400);
  }

  .stale .label {
    color: var(--warn);
  }

  .error .dot {
    background: var(--palette-300);
  }

  .error .label {
    color: var(--danger);
  }
</style>
