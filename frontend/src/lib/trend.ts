/**
 * Layout of the passing run time chart: passes in run order, idle stretches as gap breaks,
 * a rolling median per stretch of steady runs, and buckets when there are too many passes to
 * draw one dot each.
 */

import type { GateDetail } from "./api";
import { DAY } from "./format";
import { median } from "./stats";

type Pass = GateDetail["trend"][number];

/** Below this many passes the chart lists them instead of plotting a pattern. */
export const MIN_PLOTTED = 5;
/** Above this many passes the chart draws equal-count buckets instead of one dot per pass. */
export const MAX_DOTS = 500;
/** Passes in the rolling median window, centered on each pass. */
const ROLLING_WINDOW = 5;
/** The shortest idle time that counts as a gap, so overnight pauses never break the line. */
const MIN_GAP_SECONDS = DAY;
/** An idle time this many times the usual spacing counts as a gap. */
const GAP_FACTOR = 4;
/** Extra x slots a gap break takes, so it reads as a pause and not as one more run. */
const GAP_SLOTS = 1;

/** One mark on the chart: a pass, or a bucket of consecutive passes. */
export interface TrendMark {
  /** Position on the x axis, in run slots. */
  slot: number;
  /** Time of the first pass the mark covers. */
  ts: number;
  /** Time of the last pass the mark covers; equal to `ts` for a single pass. */
  endTs: number;
  /** The pass's duration, or the bucket's median. */
  duration: number;
  /** Shortest and longest pass in a bucket; equal to `duration` for a single pass. */
  min: number;
  max: number;
  /** Passes the mark covers. */
  count: number;
  /** Rolling median at this mark, or null when its stretch is too short for a trend. */
  rolling: number | null;
}

/** A pause between two runs, drawn as a band from the run before it to the run after it. */
export interface TrendGap {
  /** Slots of the last mark before the pause and the first mark after it. */
  from: number;
  to: number;
  seconds: number;
}

export interface TrendLayout {
  marks: TrendMark[];
  gaps: TrendGap[];
  /** Runs of marks between gap breaks, oldest first. */
  segments: TrendMark[][];
  /** Width of the x axis in slots, so the domain is [-0.5, slots - 0.5]. */
  slots: number;
  /** Whether each mark stands for more than one pass. */
  bucketed: boolean;
}

/**
 * Return the idle time, in seconds, past which two passes sit on either side of a gap break:
 * four times the median spacing between passes, and never less than a day.
 */
export function gapThreshold(trend: Pass[]): number {
  const spacings = trend.slice(1).map((p, i) => p.ts - trend[i]!.ts);
  return Math.max(MIN_GAP_SECONDS, GAP_FACTOR * (median(spacings) ?? 0));
}

/**
 * Return the centered rolling median of `values` over `ROLLING_WINDOW` values, shrinking at
 * the ends so the first and last values average only real neighbors. Fewer values than the
 * window give no trend.
 */
export function rollingMedian(values: number[]): (number | null)[] {
  if (values.length < ROLLING_WINDOW) return values.map(() => null);
  const half = Math.floor(ROLLING_WINDOW / 2);
  return values.map((_, i) => {
    const reach = Math.min(half, i, values.length - 1 - i);
    return median(values.slice(i - reach, i + reach + 1));
  });
}

/** Split passes, oldest first, into stretches with no gap longer than `threshold` inside. */
function splitAtGaps(trend: Pass[], threshold: number): Pass[][] {
  const stretches: Pass[][] = [];
  trend.forEach((pass, i) => {
    if (i === 0 || pass.ts - trend[i - 1]!.ts > threshold) stretches.push([]);
    stretches.at(-1)!.push(pass);
  });
  return stretches;
}

/** Return one mark per pass, or per `size` consecutive passes when `size` is more than 1. */
function marksOf(passes: Pass[], size: number): Omit<TrendMark, "slot" | "rolling">[] {
  const marks = [];
  for (let i = 0; i < passes.length; i += size) {
    const chunk = passes.slice(i, i + size);
    const durations = chunk.map((p) => p.duration);
    marks.push({
      ts: chunk[0]!.ts,
      endTs: chunk.at(-1)!.ts,
      duration: median(durations)!,
      min: Math.min(...durations),
      max: Math.max(...durations),
      count: chunk.length,
    });
  }
  return marks;
}

/**
 * Return the passes per bucket that keeps the marks at or under `MAX_DOTS`. Each stretch ends
 * in its own partial bucket, so many stretches need larger buckets than the pass count alone
 * says. More stretches than `MAX_DOTS` still give one mark per stretch at most.
 */
function bucketSize(stretches: Pass[][], total: number): number {
  const longest = Math.max(1, ...stretches.map((s) => s.length));
  const marksAt = (n: number) => stretches.reduce((sum, s) => sum + Math.ceil(s.length / n), 0);
  let size = Math.max(1, Math.ceil(total / MAX_DOTS));
  while (size < longest && marksAt(size) > MAX_DOTS) size++;
  return size;
}

/** Lay out a gate's passes, oldest first, for the passing run time chart. */
export function trendLayout(trend: Pass[]): TrendLayout {
  const stretches = splitAtGaps(trend, gapThreshold(trend));
  const size = bucketSize(stretches, trend.length);
  const marks: TrendMark[] = [];
  const gaps: TrendGap[] = [];
  const segments: TrendMark[][] = [];
  let slot = 0;
  for (const stretch of stretches) {
    const previous = marks.at(-1);
    if (previous) {
      slot += GAP_SLOTS;
      gaps.push({ from: previous.slot, to: slot, seconds: stretch[0]!.ts - previous.endTs });
    }
    const stretchMarks = marksOf(stretch, size);
    const rolling = rollingMedian(stretchMarks.map((m) => m.duration));
    const segment = stretchMarks.map(
      (m, i): TrendMark => ({ ...m, slot: slot + i, rolling: rolling[i]! }),
    );
    slot += segment.length;
    marks.push(...segment);
    segments.push(segment);
  }
  return { marks, gaps, segments, slots: slot, bucketed: size > 1 };
}

/**
 * Compare the median of the last passes with the median of the first ones: a tenth of the
 * passes at each end, never fewer than `ROLLING_WINDOW`, so one slow run among thousands moves
 * nothing. Return the signed change as a fraction and the passes in each window, or null when
 * the two windows would overlap.
 */
export function trendChange(trend: Pass[]): { change: number; window: number } | null {
  const window = Math.max(ROLLING_WINDOW, Math.round(trend.length / 10));
  if (trend.length < 2 * window) return null;
  const first = median(trend.slice(0, window).map((p) => p.duration))!;
  const last = median(trend.slice(-window).map((p) => p.duration))!;
  return first > 0 ? { change: (last - first) / first, window } : null;
}

/** Return the dot radius and opacity for `count` marks, so dense clusters read as density. */
export function dotStyle(count: number): { r: number; opacity: number } {
  if (count <= 60) return { r: 3, opacity: 1 };
  if (count <= 200) return { r: 2.25, opacity: 0.8 };
  return { r: 1.75, opacity: 0.6 };
}

/**
 * Return the slots that get a date label on an axis `width` pixels wide: the first mark, the
 * first mark after each gap break, then evenly spaced marks to fill what is left. A label
 * closer than `minGap` pixels to one already kept, or with the same `text`, is dropped.
 */
export function labelSlots(
  layout: TrendLayout,
  width: number,
  text: (slot: number) => string,
  minGap = 64,
): number[] {
  if (layout.marks.length === 0 || width <= 0) return [];
  const px = (slot: number) => ((slot + 0.5) / layout.slots) * width;
  const kept: number[] = [];
  const keptText = new Set<string>();
  const anchors = layout.segments.map((segment) => segment[0]!.slot);
  const step = Math.max(1, Math.ceil(layout.marks.length / Math.max(1, Math.floor(width / (minGap * 1.5)))));
  const fillers = layout.marks.filter((_, i) => i % step === 0).map((m) => m.slot);
  for (const slot of [...anchors, ...fillers]) {
    const label = text(slot);
    if (keptText.has(label) || kept.some((k) => Math.abs(px(k) - px(slot)) < minGap)) continue;
    kept.push(slot);
    keptText.add(label);
  }
  return kept.sort((a, b) => a - b);
}

/**
 * Return the gaps whose idle-time label fits on an axis `width` pixels wide: a label closer
 * than `minGap` pixels to the one kept before it is dropped, so close breaks never overlap.
 */
export function gapLabels(layout: TrendLayout, width: number, minGap = 32): TrendGap[] {
  const kept: TrendGap[] = [];
  let last = -Infinity;
  for (const gap of layout.gaps) {
    const px = (((gap.from + gap.to) / 2 + 0.5) / layout.slots) * width;
    if (px - last < minGap) continue;
    kept.push(gap);
    last = px;
  }
  return kept;
}
