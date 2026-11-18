<!--
  @component
  A duration in a table cell, from `ranText` or `savedText` in `src/lib/events.ts`. A missing
  value shows as a muted dash and an unrecorded one as muted "unknown", so real times stand out.

  Props:
  - `value`: the formatted time, "unknown", "not rerun", or null when the column does not apply
-->
<script lang="ts">
  interface Props {
    value: string | null;
  }

  let { value }: Props = $props();
</script>

{#if value === null}
  <span class="muted" aria-label="none">–</span>
{:else if value === "unknown" || value === "not rerun"}
  <span class="muted">{value}</span>
{:else}
  {value}
{/if}

<style>
  .muted {
    color: var(--text-faint);
  }
</style>
