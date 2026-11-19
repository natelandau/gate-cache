<!--
  @component
  Small trend lines with a fading fill, sized to their container. Decorative: the value beside
  them carries the numbers.

  Props:
  - `series`: one or more lines, each `{ values, color }`, drawn in order on one scale. `values`
    has one value per day, null for a gap; `color` is a CSS color, such as "var(--chart-saved)"
  - `highlight`: optional [from, to] day indexes to keep at full strength; the rest dim
-->
<script lang="ts" module>
  export interface SparkSeries {
    values: (number | null)[];
    color: string;
  }
</script>

<script lang="ts">
  import { sparkDomain, sparkPath } from "../sparkline";

  interface Props {
    series: SparkSeries[];
    highlight?: [from: number, to: number];
  }

  let { series, highlight }: Props = $props();

  const WIDTH = 200;
  const HEIGHT = 34;
  const uid = $props.id();
  const lines = $derived.by(() => {
    const domain = sparkDomain(series.map((s) => s.values));
    return series.map((s) => ({ color: s.color, path: sparkPath(s.values, WIDTH, HEIGHT, domain) }));
  });
  const days = $derived(Math.max(0, ...series.map((s) => s.values.length)));
  // Picked days as an x range in the path's coordinates.
  const band = $derived.by(() => {
    if (!highlight || days < 2) return null;
    const step = WIDTH / (days - 1);
    const from = Math.max(0, highlight[0] * step - step / 2);
    const to = Math.min(WIDTH, highlight[1] * step + step / 2);
    return { x: from, width: Math.max(to - from, 1) };
  });
</script>

<svg class="spark" viewBox="0 0 {WIDTH} {HEIGHT}" preserveAspectRatio="none" aria-hidden="true">
  <defs>
    {#each lines as line, i (i)}
      <linearGradient id="{uid}-fill-{i}" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stop-color={line.color} stop-opacity="0.22" />
        <stop offset="1" stop-color={line.color} stop-opacity="0" />
      </linearGradient>
    {/each}
    {#if band}
      <clipPath id="{uid}-band"><rect x={band.x} y="0" width={band.width} height={HEIGHT} /></clipPath>
    {/if}
  </defs>
  {#snippet paths()}
    {#each lines as line, i (i)}
      <path d={line.path.area} fill="url(#{uid}-fill-{i})" />
      <path d={line.path.line} fill="none" stroke={line.color} />
    {/each}
  {/snippet}
  <g class:dim={band !== null}>{@render paths()}</g>
  {#if band}
    <g clip-path="url(#{uid}-band)">{@render paths()}</g>
  {/if}
</svg>

<style>
  .spark {
    display: block;
    width: 100%;
    height: 34px;
    overflow: visible;
  }

  path[fill="none"] {
    stroke-width: 1.5;
    stroke-linejoin: round;
    stroke-linecap: round;
    vector-effect: non-scaling-stroke;
  }

  .dim {
    opacity: 0.35;
    transition: opacity var(--dur-fast) var(--ease);
  }
</style>
