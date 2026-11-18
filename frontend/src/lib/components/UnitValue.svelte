<!--
  @component
  A formatted value with its units set smaller and muted, so "6h 38m" reads as two numbers.

  Props:
  - `value`: the formatted value, such as "6h 38m" or "61%"
-->
<script lang="ts">
  import { valueParts } from "../format";

  interface Props {
    value: string;
  }

  let { value }: Props = $props();
</script>

{#each valueParts(value) as part, i (i)}{#if part.unit}<span class="u">{part.text}</span>{:else}{part.text}{/if}{/each}

<style>
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
</style>
