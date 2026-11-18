<!--
  @component
  A thin bar for a row's share of the largest row, used inline in ranked lists and bar lists.

  Props:
  - `share`: the fill, from 0 to 1
  - `color`: a CSS color for the fill, such as "var(--chart-saved)"
  - `height`: bar height in pixels (default 6)
-->
<script lang="ts">
  interface Props {
    share: number;
    color: string;
    height?: number;
  }

  let { share, color, height = 6 }: Props = $props();
</script>

<span class="track" aria-hidden="true" style:height="{height}px"
  ><span class="fill" style:width="{Math.round(Math.max(0, Math.min(1, share)) * 100)}%" style:background={color}
  ></span></span
>

<style>
  .track {
    display: block;
    border-radius: 2px;
    background: var(--track);
    overflow: hidden;
  }

  .fill {
    display: block;
    height: 100%;
    border-radius: 2px;
    transition: width var(--dur-slow) var(--ease);
  }
</style>
