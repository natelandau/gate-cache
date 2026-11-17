/**
 * The Breakdown dimensions, in menu order. Kept import-free so the router can check them. A
 * new dimension needs an entry here and one in the server's grouping registry.
 */

export interface DimensionInfo {
  readonly value: string;
  /** The group-by option and the name column's header. */
  readonly label: string;
  /** Rows cover every repo, dim the ones outside the repo filter, and pick a repo on click. */
  readonly allRepos?: boolean;
  /** Each row is one gate, so a Gates count says nothing. */
  readonly oneGate?: boolean;
}

export const DIMENSIONS = [
  { value: "repo", label: "Repo", allRepos: true },
  { value: "gate", label: "Gate", oneGate: true },
  { value: "source", label: "Source" },
  { value: "branch", label: "Branch" },
  { value: "machine", label: "Machine" },
] as const satisfies readonly DimensionInfo[];

/** What the overview's Breakdown panel groups runs by. */
export type Dimension = (typeof DIMENSIONS)[number]["value"];

export function isDimension(value: string | null): value is Dimension {
  return DIMENSIONS.some((d) => d.value === value);
}

/** Return a dimension's details. */
export function dimension(value: Dimension): DimensionInfo {
  return DIMENSIONS.find((d) => d.value === value)!;
}
