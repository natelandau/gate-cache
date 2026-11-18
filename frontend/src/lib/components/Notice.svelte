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
  import Icon from "./Icon.svelte";

  interface Props {
    tone?: "info" | "warning" | "error";
    children: Snippet;
  }

  let { tone = "info", children }: Props = $props();
</script>

<div class="notice {tone}" role={tone === "error" ? "alert" : "status"}>
  <span class="mark"
    ><Icon name={tone === "error" ? "circle-alert" : tone === "warning" ? "triangle-alert" : "info"} /></span
  >
  <p>{@render children()}</p>
</div>

<style>
  .notice {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-popover);
    background: var(--accent-soft);
    color: var(--accent);
    font-size: var(--text-sm);
  }

  p {
    margin: 0;
  }

  .mark {
    flex: none;
    display: grid;
  }

  .warning {
    background: var(--warn-soft);
    color: var(--warn);
  }

  .error {
    background: var(--danger-soft);
    color: var(--danger);
  }
</style>
