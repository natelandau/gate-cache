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
  const max = Math.max(0, ...values.map((v) => v ?? 0));
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  const bottom = height - PAD_BOTTOM;
  const y = (v: number) => (max > 0 ? bottom - (v / max) * (bottom - PAD_TOP) : bottom);
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
      return `${segment(points)} L${last[0]} ${height} L${first[0]} ${height} Z`;
    })
    .join(" ");
  return { line, area };
}

function round(n: number): number {
  return Math.round(n * 10) / 10;
}

/**
 * Split a formatted value into digits and units, so units can be set smaller: "6h 38m" gives
 * 6, h, space, 38, m. A leading sign stays with its number, and a value with no unit letters
 * comes back whole.
 */
export function valueParts(value: string): { text: string; unit: boolean }[] {
  if (!/\d/.test(value)) return [{ text: value, unit: false }];
  const parts: { text: string; unit: boolean }[] = [];
  for (const match of value.matchAll(/([−+-]?[\d.,]+)|([a-zA-Z%]+)|(\s+)|(.)/g)) {
    const [text, digits, unit] = match;
    parts.push({ text, unit: !digits && !!unit });
  }
  return parts;
}
