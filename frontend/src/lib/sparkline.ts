/** Geometry and text helpers for the headline cards' sparklines and values. */

// Room above the peak and below zero so the 1.5px stroke is never clipped.
const PAD_TOP = 4;
const PAD_BOTTOM = 2;

/**
 * Return the SVG path of a sparkline and of the area under it, scaled to `width` by `height`.
 *
 * A null value is a day with nothing to plot: the line breaks there instead of dropping to
 * zero. An empty or all-zero series draws a flat line at the bottom.
 */
export function sparkPath(
  values: (number | null)[],
  width: number,
  height: number,
): { line: string; area: string } {
  if (values.length === 0) return { line: "", area: "" };
  const known = values.filter((v): v is number => v !== null);
  const max = Math.max(0, ...known);
  // Net saved goes below zero on days that cost more than they saved, so scale from the
  // lowest value, not from zero, to keep every point inside the box.
  const min = Math.min(0, ...known);
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  const bottom = height - PAD_BOTTOM;
  const y = (v: number) => (max > min ? bottom - ((v - min) / (max - min)) * (bottom - PAD_TOP) : bottom);
  // With negative values the fill closes at zero, so it shades each value's distance from zero.
  const base = min < 0 ? round(y(0)) : height;
  const runs: [number, number][][] = [];
  let current: [number, number][] | null = null;
  values.forEach((v, i) => {
    if (v === null) {
      current = null;
      return;
    }
    if (!current) runs.push((current = []));
    current.push([round(i * step), round(y(v))]);
  });
  const segment = (points: [number, number][]) =>
    points.map(([x, py], i) => `${i ? "L" : "M"}${x} ${py}`).join(" ");
  const line = runs.map(segment).join(" ");
  const area = runs
    .map((points) => {
      const first = points[0]!;
      const last = points[points.length - 1]!;
      return `${segment(points)} L${last[0]} ${base} L${first[0]} ${base} Z`;
    })
    .join(" ");
  return { line, area };
}

function round(n: number): number {
  return Math.round(n * 10) / 10;
}
