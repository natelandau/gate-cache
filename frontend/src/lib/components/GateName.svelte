<!--
  @component
  A gate's name, with a trailing "@" and hex suffix shown muted so the readable part stands out.

  Props:
  - `name`: the gate name
-->
<script lang="ts">
  import { splitGateName } from "../gates";

  let { name }: { name: string } = $props();

  const parts = $derived(splitGateName(name));
</script>

<span class="gate-name">{parts.base}{#if parts.suffix}<span class="suffix">{parts.suffix}</span>{/if}</span>

<style>
  .suffix {
    color: var(--text-faint);
    font-weight: 400;
  }
</style>
