<!--
  @component
  LayerChart `Bars` that draw every non-zero bar at least `MIN_BAR_PX` tall, so one run among
  thousands stays visible. Use it inside a chart in place of `Bars`. The data, tooltips, and
  axes keep the true values: only the drawn height changes.

  Props:
  - `y`: the bar's [from, to] span in data units
  - `total`: for one part of a stacked bar, the whole stack's height; a short stack stretches
    as a whole to the floor, so its parts keep their proportions
  - every other prop passes through to `Bars`
-->
<script lang="ts" generics="T">
  import { getChartContext } from "layerchart";
  import { Bars, type BarsProps } from "layerchart/svg";
  import { barFloor, stackStretch, visibleValue } from "../bars";

  type Props = Omit<BarsProps, "y"> & {
    y: (d: T) => [number, number];
    total?: (d: T) => number;
  };

  let { y, total, ...rest }: Props = $props();

  const context = getChartContext<T>();
  const floor = $derived.by(() => {
    const [low, high] = context.yDomain as [number, number];
    return barFloor(high - low, context.height);
  });

  function drawn(d: T): [number, number] {
    const [from, to] = y(d);
    if (total) {
      const stretch = stackStretch(total(d), floor);
      return [from * stretch, to * stretch];
    }
    return [from, from + visibleValue(to - from, floor)];
  }
</script>

<Bars y={drawn} {...rest} />
