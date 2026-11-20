/** Geometry and text helpers for the headline cards' sparklines and values. */

// Room above the peak and below zero so the 1.5px stroke is never clipped.
const PAD_TOP = 4;
const PAD_BOTTOM = 2;

/**
 * Return the SVG path of a sparkline and of the area under it, scaled to `width` by `height`.
 *
 * A null value is a day with nothing to plot: the line breaks there instead of dropping to
 * zero. An empty or all-zero series draws a flat line at the bottom. Pass `domain`, from
 * `sparkDomain`, to draw several series on one scale.
 */
export function sparkPath(
  values: (number | null)[],
  width: number,
  height: number,
  domain: [min: number, max: number] = sparkDomain([values]),
): { line: string; area: string } {
  if (values.length === 0) return { line: "", area: "" };
  const [min, max] = domain;
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
  const segment = (points: [number, number][]) => {
    const [x0, y0] = points[0]!;
    // A lone known day gets a zero-length segment: with a round line cap it draws as a dot.
    if (points.length === 1) return `M${x0} ${y0} h0`;
    const slopes = monotoneSlopes(points);
    const curves = points.slice(1).map(([x, py], i) => {
      const [px, pyPrev] = points[i]!;
      const dx = (x - px) / 3;
      return `C${round(px + dx)} ${round(pyPrev + dx * slopes[i]!)} ${round(x - dx)} ${round(py - dx * slopes[i + 1]!)} ${x} ${py}`;
    });
    return `M${x0} ${y0} ${curves.join(" ")}`;
  };
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

/**
 * Return the lowest and highest value to scale sparklines to, across every series. The range
 * always takes in zero, and values can go below zero, so it starts at the lowest value to
 * keep every point inside the box.
 */
export function sparkDomain(series: (number | null)[][]): [min: number, max: number] {
  const known = series.flat().filter((v): v is number => v !== null);
  return [Math.min(0, ...known), Math.max(0, ...known)];
}

/**
 * Return the tangent slope at each point for a monotone cubic curve (Fritsch-Carlson, as in
 * d3's curveMonotoneX). The curve never overshoots a point, so it stays between zero and the
 * peak and never invents a dip or spike the data does not have.
 */
function monotoneSlopes(points: [number, number][]): number[] {
  const secants = points.slice(1).map(([x, y], i) => {
    const [px, py] = points[i]!;
    return x === px ? 0 : (y - py) / (x - px);
  });
  if (secants.length === 1) return [secants[0]!, secants[0]!];
  const inner = secants.slice(1).map((s1, i) => {
    const s0 = secants[i]!;
    if (s0 * s1 <= 0) return 0;
    const h0 = points[i + 1]![0] - points[i]![0];
    const h1 = points[i + 2]![0] - points[i + 1]![0];
    const mean = (s0 * h1 + s1 * h0) / (h0 + h1);
    return Math.sign(s0) * Math.min(2 * Math.abs(s0), 2 * Math.abs(s1), Math.abs(mean));
  });
  // An end tangent bends toward its neighbor's, so the curve leaves the end smoothly.
  const end = (secant: number, neighbor: number) => (3 * secant - neighbor) / 2;
  return [end(secants[0]!, inner[0]!), ...inner, end(secants[secants.length - 1]!, inner[inner.length - 1]!)];
}

function round(n: number): number {
  return Math.round(n * 10) / 10;
}
