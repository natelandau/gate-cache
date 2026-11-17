/** Labels and text for recorded events. */

import type { EventRow, Outcome } from "./api";
import { formatDuration, formatTimestamp } from "./format";

export type OutcomeTone = "accent" | "ok" | "info" | "danger" | "neutral";

/** How each outcome reads in the UI. `description` is the hover text of its badge. */
export const OUTCOMES: Record<Outcome, { label: string; tone: OutcomeTone; description: string }> = {
  skip: {
    label: "Skip",
    tone: "accent",
    description: "Skipped: the command already passed on this tree.",
  },
  pass: { label: "Pass", tone: "ok", description: "Ran and passed; the pass was cached." },
  pass_unrecorded: {
    label: "Pass, not cached",
    tone: "info",
    description: "Ran and passed, but the pass was not cached because the files changed.",
  },
  fail: { label: "Fail", tone: "danger", description: "Ran and failed." },
  uncached: { label: "Uncached", tone: "neutral", description: "Ran without the cache." },
};

/** Return "saved 1m 31s" for a skip, "ran 54s" for a run, or "not rerun" for a reported failure. */
export function timeText(event: EventRow): string {
  if (event.reported) return "not rerun";
  const skip = event.outcome === "skip";
  const seconds = skip ? event.saved : event.duration;
  const verb = skip ? "saved" : "ran";
  return seconds === null ? `${verb}, time unknown` : `${verb} ${formatDuration(seconds)}`;
}

/** Return the first 10 characters of a git tree hash, or "" without one. */
export function shortTree(tree: string | null): string {
  return tree ? tree.slice(0, 10) : "";
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
