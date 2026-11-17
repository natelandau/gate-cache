<!--
  @component
  A one-line banner above page content. Use `info` for state the user can change, `warning`
  for degraded data, `error` for failures.

  Props:
  - `tone`: "info" | "warning" | "error" (default "info")
  - `children`: the message; may contain inline markup such as `<code>`
-->
<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    tone?: "info" | "warning" | "error";
    children: Snippet;
  }

  let { tone = "info", children }: Props = $props();
</script>

<div class="notice {tone}" role={tone === "error" ? "alert" : "status"}>
  <span class="mark" aria-hidden="true"></span>
  <p>{@render children()}</p>
</div>

<style>
  .notice {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: 6px var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    font-size: var(--text-md);
  }

  p {
    margin: 0;
  }

  .mark {
    flex: none;
    width: 3px;
    align-self: stretch;
    border-radius: 2px;
    background: var(--accent);
  }

  .warning {
    background: var(--warn-soft);
  }

  .warning .mark {
    background: var(--warn);
  }

  .error {
    background: var(--danger-soft);
  }

  .error .mark {
    background: var(--danger);
  }
</style>
