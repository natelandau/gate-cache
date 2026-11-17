import type { RepoRow } from "./api";
import type { RepoOption } from "./components/RepoPicker.svelte";
import { UNKNOWN_REPO } from "./router.svelte";

/**
 * Return repo picker options sorted by label. The API already gives repos sharing a folder name
 * distinct names. Events recorded without a repo get a last option with the value `-`, labeled
 * with the API's name for them.
 */
export function repoOptions(rows: Pick<RepoRow, "repo" | "repo_name">[]): RepoOption[] {
  const known = rows.filter((row): row is { repo: string; repo_name: string } => row.repo !== null);
  const options: RepoOption[] = known
    .map((row) => ({ value: row.repo, label: row.repo_name, title: row.repo }))
    .sort((a, b) => a.label.localeCompare(b.label));
  const unknown = rows.find((row) => row.repo === null);
  if (unknown) options.push({ value: UNKNOWN_REPO, label: unknown.repo_name });
  return options;
}

/** The API's name for events recorded without a repo, used before the repo list loads. */
const UNKNOWN_REPO_LABEL = "unknown repo";

/** Return the display name of a selected repo: its picker label, else its directory name. */
export function repoLabel(repo: string, options: RepoOption[]): string {
  const option = options.find((o) => o.value === repo);
  if (option) return option.label;
  if (repo === UNKNOWN_REPO) return UNKNOWN_REPO_LABEL;
  const parts = repo.replace(/\/\.git\/?$/, "").split("/");
  return parts.at(-1) || repo;
}

/**
 * Return the display name of a repo selection: the repo's name when one is selected, a count
 * such as "3 repos" for several, and null for every repo.
 */
export function repoSelectionLabel(repos: string[], options: RepoOption[]): string | null {
  if (repos.length === 0) return null;
  if (repos.length === 1) return repoLabel(repos[0]!, options);
  return `${repos.length} repos`;
}
