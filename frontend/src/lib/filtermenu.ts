/**
 * The Activity page's Filter menu: its sections, the choices of each filter, and the filter a
 * pick applies. A filter picked here is the same filter a link applies.
 */

import { without } from "./activity";
import type { ActivityFilter, ActivityGroup, BreakdownRow, GateRef, GateRow, Outcome, ReasonRow } from "./api";
import { rowGroup } from "./breakdown";
import type { Dimension } from "./dimensions";
import { OUTCOMES } from "./events";
import { gateKey } from "./gates";
import { ACTIVITY_FILTERS } from "./terms";

/** One entry of the menu, named by the filter key it sets. */
export type FilterKind = keyof ActivityFilter;

/** The filters that hold a list of values. */
export type ListKind = "outcome" | "gate" | "reason";

/** The filters that switch on and off, with no value. */
export type ToggleKind = "flaky" | "spotCheck";

export interface MenuEntry {
  kind: FilterKind;
  label: string;
}

export interface MenuSection {
  title: string;
  /** Entries that apply at once as checkboxes, rather than open a picker. */
  toggles?: true;
  entries: MenuEntry[];
}

export const MENU_SECTIONS: MenuSection[] = [
  {
    title: ACTIVITY_FILTERS.sections.run,
    entries: [
      { kind: "outcome", label: ACTIVITY_FILTERS.outcome },
      { kind: "gate", label: ACTIVITY_FILTERS.gate },
      { kind: "reason", label: ACTIVITY_FILTERS.reason },
    ],
  },
  { title: ACTIVITY_FILTERS.sections.when, entries: [{ kind: "span", label: ACTIVITY_FILTERS.days }] },
  { title: ACTIVITY_FILTERS.sections.group, entries: [{ kind: "group", label: ACTIVITY_FILTERS.group }] },
  {
    title: ACTIVITY_FILTERS.sections.only,
    toggles: true,
    entries: [
      { kind: "flaky", label: ACTIVITY_FILTERS.flaky },
      { kind: "spotCheck", label: ACTIVITY_FILTERS.spotCheck },
    ],
  },
];

/** Return the menu entry of a filter that opens a picker, or undefined for a toggle. */
export function pickerEntry(kind: FilterKind): MenuEntry | undefined {
  return MENU_SECTIONS.filter((section) => !section.toggles)
    .flatMap((section) => section.entries)
    .find((entry) => entry.kind === kind);
}

/** One option of a picker, with the value it adds to the filter. */
export interface ListChoice<T> {
  value: string;
  label: string;
  item: T;
}

/** One option of the Group picker, with the group it applies. */
export type GroupChoice = ListChoice<ActivityGroup>;

function byLabel<C extends { label: string }>(choices: C[]): C[] {
  return choices.sort((a, b) => a.label.localeCompare(b.label));
}

/**
 * Return `choices` with each applied pick the list lacks first, such as a gate applied by a
 * link that has no runs in the range, so the list can show what is applied.
 */
function withCurrent<C extends { value: string }>(choices: C[], current: C[]): C[] {
  const missing = current.filter((own) => !choices.some((choice) => choice.value === own.value));
  return [...missing, ...choices];
}

/** Return a choice per outcome, in the badge order. */
export function outcomeChoices(): ListChoice<Outcome>[] {
  return (Object.keys(OUTCOMES) as Outcome[]).map((outcome) => ({
    value: outcome,
    label: OUTCOMES[outcome].label,
    item: outcome,
  }));
}

/** Return a choice per gate, by name. Names carry their repo when the gates span repos. */
export function gateChoices(
  rows: Pick<GateRow, "repo" | "repo_name" | "name">[],
  current: GateRef[] = [],
): ListChoice<GateRef>[] {
  const manyRepos = new Set(rows.map((row) => row.repo)).size > 1;
  const choices = rows.map((row) => {
    const gate = { repo: row.repo, name: row.name };
    return { value: gateKey(gate), label: manyRepos ? `${row.name} (${row.repo_name})` : row.name, item: gate };
  });
  const own = current.map((gate) => ({ value: gateKey(gate), label: gate.name, item: gate }));
  return withCurrent(byLabel(choices), own);
}

/** Return a choice per distinct reason. A reason can come with more than one outcome. */
export function reasonChoices(rows: Pick<ReasonRow, "reason">[], current: string[] = []): ListChoice<string>[] {
  const choice = (reason: string) => ({ value: reason, label: reason, item: reason });
  const reasons = [...new Set(rows.map((row) => row.reason))];
  return withCurrent(byLabel(reasons.map(choice)), current.map(choice));
}

/** Return a choice per Breakdown row of `by`, keeping `current` when it groups by `by`. */
export function groupChoices(
  by: Dimension,
  rows: Pick<BreakdownRow, "key" | "label">[],
  current?: ActivityGroup,
): GroupChoice[] {
  const choices = rows.map((row) => ({ value: row.key, label: row.label, item: rowGroup(by, row) }));
  const own = current?.by === by ? [{ value: current.key, label: current.label, item: current }] : [];
  return withCurrent(byLabel(choices), own);
}

/** Return the values of a list filter that its picker shows as checked. */
export function listValues(filter: ActivityFilter, kind: ListKind): string[] {
  if (kind === "gate") return (filter.gate ?? []).map(gateKey);
  return filter[kind] ?? [];
}

/** Return `filter` with a list filter set to `items`, or removed when `items` is empty. */
export function withList<K extends ListKind>(
  filter: ActivityFilter,
  kind: K,
  items: NonNullable<ActivityFilter[K]>,
): ActivityFilter {
  const next = without(filter, kind);
  return items.length ? { ...next, [kind]: items } : next;
}

/** Return `filter` with a toggle switched on or off. */
export function withToggle(filter: ActivityFilter, kind: ToggleKind, on: boolean): ActivityFilter {
  const next = without(filter, kind);
  return on ? { ...next, [kind]: true } : next;
}
