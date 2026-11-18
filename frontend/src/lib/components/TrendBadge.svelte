<!--
  @component
  A change as a chip: a trend arrow, a hidden "Up" or "Down" for screen readers, and the
  amount. The tone says whether the change is good, so color never carries the direction.

  Props:
  - `dir`: "up", "down", or null for no change (no arrow)
  - `text`: the amount, such as "6%", or "No change"
  - `tone`: "good", "bad", or "neutral"
-->
<script lang="ts">
  import Badge from "./Badge.svelte";
  import Icon from "./Icon.svelte";

  interface Props {
    dir: "up" | "down" | null;
    text: string;
    tone: "good" | "bad" | "neutral";
  }

  let { dir, text, tone }: Props = $props();

  const TONES = { good: "ok", bad: "danger", neutral: "neutral" } as const;
</script>

<Badge tone={TONES[tone]}
  ><span class="trend {tone}"
    >{#if dir}<Icon name={dir === "up" ? "trending-up" : "trending-down"} size={12} /><span
        class="visually-hidden">{dir === "up" ? "Up" : "Down"}</span
      >{/if}{text}</span
  ></Badge
>

<style>
  .trend {
    display: inline-flex;
    align-items: center;
    gap: 3px;
  }
</style>
