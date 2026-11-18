<!--
  @component
  A gate's name. When the name carries a key, such as "@c350b4abb3f3" after its gate, the key
  shows muted so the gate stands out. A command line, the name of a gate run without --name,
  stays on one line and ends in an ellipsis, with the whole command on hover.

  Props:
  - `name`: the gate name, key included
  - `gate`: the gate that the name counts toward, as the server reports it; omit it when
    `name` is already the gate
-->
<script lang="ts">
  import { isCommandLine } from "../gates";

  let { name, gate = name }: { name: string; gate?: string } = $props();

  const suffix = $derived(gate !== name && name.startsWith(gate) ? name.slice(gate.length) : "");
  const command = $derived(isCommandLine(name));
</script>

<span class="gate-name" class:command title={command ? name : undefined}
  >{suffix ? gate : name}{#if suffix}<span class="suffix">{suffix}</span>{/if}</span
>

<style>
  .suffix {
    color: var(--text-faint);
    font-weight: 400;
  }

  /* A fixed cap rather than the container's width, so the ellipsis works in an auto-sized
     table cell and no caller needs a wrapper. */
  .command {
    display: inline-block;
    max-width: min(100%, 320px);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    vertical-align: bottom;
  }
</style>
