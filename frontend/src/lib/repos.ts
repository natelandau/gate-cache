import type { RepoRow } from "./api";
import type { RepoOption } from "./components/RepoFilter.svelte";

/** Return the directory that holds a repo's working copy, such as `code` for `/a/code/app/.git`. */
function parentDir(path: string): string {
  const parts = path.replace(/\/\.git\/?$/, "").split("/");
  return parts.slice(-2, -1)[0] || path;
}

/**
 * Return repo picker options sorted by label. Repos sharing a name get their parent directory
 * appended so each label is distinct. Events with no known repo cannot be filtered on, so they
 * get no option.
 */
export function repoOptions(rows: Pick<RepoRow, "repo" | "repo_name">[]): RepoOption[] {
  const known = rows.filter((row): row is { repo: string; repo_name: string } => row.repo !== null);
  const counts = new Map<string, number>();
  for (const row of known) counts.set(row.repo_name, (counts.get(row.repo_name) ?? 0) + 1);
  return known
    .map((row) => ({
      value: row.repo,
      label:
        (counts.get(row.repo_name) ?? 0) > 1 ? `${row.repo_name} (${parentDir(row.repo)})` : row.repo_name,
      title: row.repo,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

/**
 * Return the display name of a selected repo: its picker label, else its directory name. Null
 * (all repos) stays null.
 */
export function repoLabel(repo: string | null, options: RepoOption[]): string | null {
  if (repo === null) return null;
  const option = options.find((o) => o.value === repo);
  if (option) return option.label;
  const parts = repo.replace(/\/\.git\/?$/, "").split("/");
  return parts.at(-1) || repo;
}
