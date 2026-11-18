<!--
  @component
  A small trend line with a fading fill, sized to its container. Decorative: the value beside
  it carries the number.

  Props:
  - `values`: one value per day; null leaves a gap
  - `color`: a CSS custom property name for the line, such as "--chart-saved"
  - `highlight`: optional [from, to] day indexes to keep at full strength; the rest dim
-->
<script lang="ts">
  import { sparkPath } from "../sparkline";

  interface Props {
    values: (number | null)[];
    color: string;
    highlight?: [from: number, to: number];
  }

  let { values, color, highlight }: Props = $props();

  const WIDTH = 200;
  const HEIGHT = 34;
  const uid = $props.id();
  const path = $derived(sparkPath(values, WIDTH, HEIGHT));
  const stroke = $derived(`var(${color})`);
  // Picked days as an x range in the path's coordinates.
  const band = $derived.by(() => {
    if (!highlight || values.length < 2) return null;
    const step = WIDTH / (values.length - 1);
    const from = Math.max(0, highlight[0] * step - step / 2);
    const to = Math.min(WIDTH, highlight[1] * step + step / 2);
    return { x: from, width: Math.max(to - from, 1) };
  });
</script>

<svg class="spark" viewBox="0 0 {WIDTH} {HEIGHT}" preserveAspectRatio="none" aria-hidden="true">
  <defs>
    <linearGradient id="{uid}-fill" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color={stroke} stop-opacity="0.22" />
      <stop offset="1" stop-color={stroke} stop-opacity="0" />
    </linearGradient>
    {#if band}
      <clipPath id="{uid}-band"><rect x={band.x} y="0" width={band.width} height={HEIGHT} /></clipPath>
    {/if}
  </defs>
  <g class:dim={band !== null}>
    <path d={path.area} fill="url(#{uid}-fill)" />
    <path d={path.line} fill="none" stroke={stroke} />
  </g>
  {#if band}
    <g clip-path="url(#{uid}-band)">
      <path d={path.area} fill="url(#{uid}-fill)" />
      <path d={path.line} fill="none" stroke={stroke} />
    </g>
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
