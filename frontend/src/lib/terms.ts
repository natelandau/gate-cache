/**
 * The dashboard's names for what it counts, in one place, so every card, column, tab, tooltip,
 * and empty state uses the same words. "Calls" are every time a gate was called, skipped or
 * not; "time ran" is how long commands actually ran; "saved by cache" is run time that skips
 * avoided.
 */
const SPOT_CHECKS_ABOUT =
  "Calls that would have been skipped, but ran the command anyway to confirm that the cache " +
  "is still right. They count as runs, not as skips.";

export const TERMS = {
  calls: {
    label: "Gate calls",
    column: "Calls",
    one: "gate call",
    many: "gate calls",
    about: "Every time a gate was called through gate-cache, whether its command ran or the cache skipped it.",
  },
  ran: {
    label: "Time gates ran",
    column: "Time ran",
    noun: "run time",
    about:
      "Total time of the calls that ran, failed runs included. Skipped calls take no time, and " +
      "gate-cache overhead and waits are not counted.",
  },
  failures: { label: "Gate failures", column: "Failures", one: "failure", many: "failures" },
  flaky: { label: "Flaky gates" },
  spotChecks: {
    label: "Spot checks",
    column: "Spot checks",
    badge: "Spot check",
    about: SPOT_CHECKS_ABOUT,
    aboutCard:
      `${SPOT_CHECKS_ABOUT} The failed count shows how many spot checks failed, which means an ` +
      "earlier pass was wrong, often because the gate's name or paths miss an input.",
    ran: "ran",
    failed: "failed",
  },
  skipRate: {
    label: "Cache skip rate",
    column: "Cache skip %",
    about:
      "The share of calls that checked the cache and were skipped because the same gate " +
      "already passed on the same content. Calls with caching off are left out.",
  },
  saved: {
    label: "Saved by cache",
    column: "Saved by cache",
    noun: "time saved by cache",
    about: "Run time that skipped calls did not spend, taken from the earlier passing run that let each one skip.",
  },
} as const;

/**
 * The Triage page's words. Each key of `reasons` is a reason a gate needs a look, as the API
 * names it, with its badge, its one-line explanation, and the noun its empty state uses.
 */
export const TRIAGE = {
  title: "Triage",
  lede: "Gates that need a look, newest first. Each row names one reason and the runs behind it.",
  filter: "Reason",
  allReasons: "All reasons",
  otherReasons: "Pick All reasons to see the gates listed for other reasons.",
  subject: "gates to triage",
  definition:
    "A gate shows here when the same tree both failed and passed, when a test passed only on a retry, " +
    "or when a spot check failed.",
  reasons: {
    flaky: {
      badge: "Flaky",
      line:
        "The same tree both failed and passed, or a test passed only on a retry. Look for a test that " +
        "depends on timing, order, or outside state.",
      subject: "flaky gates",
    },
    failed_spot_check: {
      badge: "Failed spot check",
      line:
        "This gate had passed on this tree, then failed when run again. Either a test is flaky, or " +
        "the gate's name and paths miss an input that changed.",
      subject: "failed spot checks",
    },
  },
  exitCode: "exit code",
  allSpotChecks: "All in Activity",
  shownOf: (shown: string, total: string) => `${shown} of ${total} shown`,
} as const;

/**
 * The Activity page's page-local filters: the Filter menu's sections and entries, and the text
 * of each filter's chip.
 */
export const ACTIVITY_FILTERS = {
  button: "Filter",
  caption: "Activity filters",
  clearAll: "Clear all",
  back: "Back",
  apply: "Apply",
  sections: { run: "Run", when: "When", group: "Group", only: "Only" },
  outcome: "Outcome",
  gate: "Gate",
  reason: "Reason",
  group: "Group by",
  days: "Date range",
  flaky: "Flaky trees",
  spotCheck: "Spot checks",
  flakyChip: "Flaky trees only",
  spotCheckChip: "Spot checks only",
  /** The chip of a filter with values, such as "Outcome is Fail, Skip". */
  chip: (name: string, values: string[]) => `${name} is ${values.join(", ")}`,
} as const;

/** Return `count` with the singular or plural noun of a counted term, such as "1 gate call". */
export function counted(count: number, term: { one: string; many: string }, format: (n: number) => string): string {
  return `${format(count)} ${count === 1 ? term.one : term.many}`;
}
