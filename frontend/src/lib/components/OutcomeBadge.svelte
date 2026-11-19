<!--
  @component
  The outcome of one event as a colored label, with a hover text that explains it.

  Props:
  - `outcome`: the event outcome
  - `title`: hover text; defaults to the outcome's description
  - `spotCheck`: when true, a neutral "Spot check" badge follows the outcome
-->
<script lang="ts">
  import type { Outcome } from "../api";
  import { OUTCOMES } from "../events";
  import { TERMS } from "../terms";
  import Badge from "./Badge.svelte";

  interface Props {
    outcome: Outcome;
    title?: string;
    spotCheck?: boolean;
  }

  let { outcome, title, spotCheck = false }: Props = $props();

  const info = $derived(OUTCOMES[outcome]);
</script>

<Badge tone={info.tone} title={title ?? info.description}>{info.label}</Badge>{#if spotCheck}
  <Badge title={TERMS.spotChecks.about}>{TERMS.spotChecks.badge}</Badge>{/if}
