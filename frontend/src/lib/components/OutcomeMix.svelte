<!--
  @component
  The share of each outcome as one stacked bar, with a legend that lists every outcome, its
  count, and its percent, drawn with `ShareMix`.

  Props:
  - `counts`: runs per outcome; pass a nonzero total
  - `href`: optional link for an outcome's runs; links each non-zero count and bar segment
-->
<script lang="ts">
  import type { Outcome } from "../api";
  import { OUTCOMES } from "../events";
  import type { MixPart } from "../rank";
  import ShareMix from "./ShareMix.svelte";

  interface Props {
    counts: Record<Outcome, number>;
    href?: (outcome: Outcome) => string;
  }

  let { counts, href }: Props = $props();

  const COLORS: Record<Outcome, string> = {
    skip: "var(--chart-skip)",
    pass: "var(--chart-pass)",
    pass_unrecorded: "var(--chart-pass-unrecorded)",
    fail: "var(--chart-fail)",
    uncached: "var(--chart-uncached)",
  };

  const parts: MixPart[] = $derived(
    (Object.keys(OUTCOMES) as Outcome[]).map((outcome) => ({
      key: outcome,
      label: OUTCOMES[outcome].long,
      count: counts[outcome],
      color: COLORS[outcome],
      href: href?.(outcome),
    })),
  );
</script>

<ShareMix {parts} />
