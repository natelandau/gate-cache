/**
 * The dashboard's names for what it counts, in one place, so every card, column, tab, tooltip,
 * and empty state uses the same words. "Calls" are every time a gate was called, skipped or
 * not; "time ran" is how long commands actually ran; "saved by cache" is run time that skips
 * avoided.
 */
export const TERMS = {
  calls: { label: "Gate calls", column: "Calls", one: "gate call", many: "gate calls" },
  ran: { label: "Time gates ran", column: "Time ran", noun: "run time" },
  failures: { label: "Gate failures", column: "Failures", one: "failure", many: "failures" },
  flaky: { label: "Flaky gates" },
  skipRate: { label: "Cache skip rate", column: "Cache skip %" },
  saved: { label: "Time saved by cache", column: "Saved by cache", noun: "time saved by cache" },
  net: { label: "Net saved by cache" },
} as const;

/** Return `count` with the singular or plural noun of a counted term, such as "1 gate call". */
export function counted(count: number, term: { one: string; many: string }, format: (n: number) => string): string {
  return `${format(count)} ${count === 1 ? term.one : term.many}`;
}
