/** Copy and rows for the module that shows runs waiting for a concurrent run of the same gate. */

import type { Coalescing } from "./api";
import { formatCount, formatDuration, formatPercent, plural } from "./format";
import type { MixPart } from "./rank";

/** One headline number of the module. */
export interface WaitFact {
  label: string;
  value: string;
}

/** Return how the waits ended, in a fixed order: skips blue and failures red, as in every chart. */
export function waitEndings(c: Coalescing): MixPart[] {
  return [
    {
      key: "skipped",
      label: "Skipped",
      title: "Waited, then skipped because the other run passed.",
      count: c.skipped,
      color: "var(--chart-skip)",
    },
    {
      key: "reported",
      label: "Reported its failure",
      title: "Waited, then exited with the other run's failure instead of running again.",
      count: c.reported,
      color: "var(--chart-fail)",
    },
    {
      key: "ran",
      label: "Ran anyway",
      title:
        "Waited, then ran the command: the other run did not pass, the files changed, or the wait timed out.",
      count: c.ran,
      color: "var(--chart-neutral)",
    },
  ];
}

/** Return the wait totals: how many calls waited, the total and typical wait, and what it saved. */
export function waitFacts(c: Coalescing): WaitFact[] {
  return [
    {
      label: "Calls that waited",
      value: `${formatCount(c.waited)} (${formatPercent(c.runs ? c.waited / c.runs : null)})`,
    },
    { label: "Total wait", value: formatDuration(c.total_wait) },
    { label: "Typical wait", value: formatDuration(c.median_wait) },
    { label: "Saved by skips after a wait", value: formatDuration(c.saved) },
  ];
}

/**
 * Return the footnote for what the numbers leave out: waits that hit the timeout, and runs from a
 * gate-cache that did not record waits. Undefined when there is neither.
 */
export function coalescingNote(c: Coalescing): string | undefined {
  const notes: string[] = [];
  if (c.timed_out) notes.push(`${plural(c.timed_out, "wait", "waits")} reached the timeout.`);
  if (c.unknown_runs) {
    notes.push(
      `${plural(c.unknown_runs, "call", "calls")} in this range came from an older gate-cache that did not record waits, so ${c.unknown_runs === 1 ? "it is" : "they are"} not counted here.`,
    );
  }
  return notes.length ? notes.join(" ") : undefined;
}

/** What a run waits for, for the empty state. */
export const COALESCING_HINT =
  "A run waits when another run of the same gate on the same files is in progress, then skips if that run passes.";
