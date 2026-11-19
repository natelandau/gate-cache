/** Labels and text for recorded events. */

import type { EventRow, Outcome } from "./api";
import { formatDuration, formatTimestamp } from "./format";

export type OutcomeTone = "accent" | "ok" | "info" | "danger" | "neutral";

/**
 * How each outcome reads in the UI. `label` is the short badge text, `long` names the outcome
 * where there is room, such as a legend, and `description` is the hover text of its badge.
 */
export const OUTCOMES: Record<Outcome, { label: string; long: string; tone: OutcomeTone; description: string }> = {
  skip: {
    label: "Skip",
    long: "Skipped by cache",
    tone: "accent",
    description: "Skipped: the command already passed on this tree.",
  },
  pass: { label: "Pass", long: "Ran and passed", tone: "ok", description: "Ran and passed; the pass was cached." },
  pass_unrecorded: {
    label: "Pass (not cached)",
    long: "Passed, pass not cached",
    tone: "info",
    description: "Ran and passed, but the pass was not cached because the files changed.",
  },
  fail: { label: "Fail", long: "Ran and failed", tone: "danger", description: "Ran and failed." },
  uncached: { label: "Uncached", long: "Ran with cache off", tone: "neutral", description: "Ran without the cache." },
};

/** The time text of a reported failure, which did not run its command. */
export const NOT_RERUN = "not rerun";
/** The time text when no time was recorded. */
export const UNKNOWN_TIME = "unknown";

/**
 * Return the run time of an event for a "Ran for" column: "not rerun" for a reported failure,
 * null for a skip, which did not run, and "unknown" when no time was recorded.
 */
export function ranText(event: EventRow): string | null {
  if (event.reported) return NOT_RERUN;
  if (event.outcome === "skip") return null;
  return event.duration === null ? UNKNOWN_TIME : formatDuration(event.duration);
}

/**
 * Return the time a skip saved for a "Saved" column: null for anything that is not a skip,
 * and "unknown" when the skip's saving was not recorded.
 */
export function savedText(event: EventRow): string | null {
  if (event.outcome !== "skip") return null;
  return event.saved === null ? UNKNOWN_TIME : formatDuration(event.saved);
}

/** Return "saved 1m 31s" for a skip, "ran 54s" for a run, or "not rerun" for a reported failure, as one phrase for hover text. */
export function timeText(event: EventRow): string {
  if (event.reported) return NOT_RERUN;
  const skip = event.outcome === "skip";
  const seconds = skip ? event.saved : event.duration;
  const verb = skip ? "saved" : "ran";
  return seconds === null ? `${verb}, time unknown` : `${verb} ${formatDuration(seconds)}`;
}

/** Return the first 10 characters of a git tree hash, or "" without one. */
export function shortTree(tree: string | null): string {
  return tree ? tree.slice(0, 10) : "";
}

/** Return the hover text for a run's outcome badge: its details and its time. */
export function runTitle(event: EventRow): string {
  return `${eventTitle(event)} · ${timeText(event)}`;
}

/** Return the key a run's name adds to its gate, such as "@v2", or "" when it has none. */
export function runSuffix(event: EventRow): string {
  return event.name.slice(event.gate.length);
}

/** Return the hover text for an event: outcome, time, and whichever details it has. */
export function eventTitle(event: EventRow): string {
  const parts = [OUTCOMES[event.outcome].label, formatTimestamp(event.ts)];
  if (event.exit_code !== null && event.exit_code !== 0) parts.push(`exit code ${event.exit_code}`);
  if (event.reason) parts.push(event.reason);
  if (event.tree) parts.push(`tree ${event.tree}`);
  return parts.join(" · ");
}

/**
 * Return a key per event that survives refreshes: events carry no id, so the key is the
 * event's fields plus how many identical events came before it.
 */
export function eventKeys(events: EventRow[]): string[] {
  const seen = new Map<string, number>();
  return events.map((event) => {
    const base = JSON.stringify([event.ts, event.name, event.repo, event.outcome]);
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    return `${base}#${count}`;
  });
}
