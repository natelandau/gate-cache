<!--
  @component
  The outcome of one event as a colored label, with a hover text that explains it.

  Props:
  - `outcome`: the event outcome
  - `title`: hover text; defaults to the outcome's description
-->
<script lang="ts">
  import type { Outcome } from "../api";
  import { OUTCOMES } from "../events";
  import Badge from "./Badge.svelte";

  interface Props {
    outcome: Outcome;
    title?: string;
  }

  let { outcome, title }: Props = $props();

  const info = $derived(OUTCOMES[outcome]);
</script>

<Badge tone={info.tone} title={title ?? info.description}>{info.label}</Badge>
