<!--
  @component
  The repo filter: a button that shows the selection and opens a list of native checkboxes.
  "All repos" comes first and means no repo filter. Checking it clears the other repos, checking
  a repo unchecks it, and unchecking the last repo checks it again.

  Props:
  - `options`: the repos to offer, each `{ value, label, title? }` where `value` is the git
    common directory, or `-` for the unknown repo, and `title` the full path shown on hover
  - `value`: the selected repos; empty for all repos
  - `onchange`: called with the new selection; empty for all repos
-->
<script lang="ts" module>
  export interface RepoOption {
    value: string;
    label: string;
    title?: string;
  }

  /**
   * Return the selection after a checkbox changes. A `value` of null is "All repos", and
   * checking it selects every repo, which is the empty selection.
   */
  export function toggleRepo(current: string[], value: string | null, checked: boolean): string[] {
    if (value === null) return [];
    if (!checked) return current.filter((repo) => repo !== value);
    return current.includes(value) ? current : [...current, value];
  }
</script>

<script lang="ts">
  import { repoLabel, repoSelectionLabel } from "../repos";
  import Dropdown from "./Dropdown.svelte";

  interface Props {
    options: RepoOption[];
    value: string[];
    onchange: (repos: string[]) => void;
  }

  let { options, value, onchange }: Props = $props();

  // Keep selected repos listed even when the option list does not include them yet.
  const shown = $derived([
    ...options,
    ...value
      .filter((repo) => !options.some((o) => o.value === repo))
      .map((repo) => ({ value: repo, label: repoLabel(repo, options), title: repo })),
  ]);
  const all = $derived(value.length === 0);
  const label = $derived(repoSelectionLabel(value, options) ?? "All repos");
  const title = $derived(value.length === 1 ? shown.find((o) => o.value === value[0])?.title : undefined);

  function change(event: Event & { currentTarget: HTMLInputElement }, repo: string | null) {
    const next = toggleRepo(value, repo, event.currentTarget.checked);
    // Unchecking "All repos" alone leaves the selection empty, so the box must stay checked.
    if (repo === null) event.currentTarget.checked = true;
    onchange(next);
  }
</script>

<Dropdown caption="Repos" {label} {title} width="240px">
  {#snippet icon()}
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round">
      <path d="M1.75 4.25v8a1 1 0 0 0 1 1h10.5a1 1 0 0 0 1-1v-6.5a1 1 0 0 0-1-1H8L6.5 3H2.75a1 1 0 0 0-1 1.25z" />
    </svg>
  {/snippet}
  {#snippet children()}
    <fieldset class="list">
      <legend class="visually-hidden">Repos to show</legend>
      <label>
        <input type="checkbox" checked={all} onchange={(event) => change(event, null)} />
        <span>All repos</span>
      </label>
      <hr />
      <div class="repos">
        {#each shown as option (option.value)}
          <label title={option.title}>
            <input
              type="checkbox"
              checked={value.includes(option.value)}
              onchange={(event) => change(event, option.value)}
            />
            <span>{option.label}</span>
          </label>
        {/each}
      </div>
    </fieldset>
    <p class="hint">Checking "All repos" clears the others.</p>
  {/snippet}
</Dropdown>

<style>
  .list {
    margin: 0;
    padding: 0;
    border: 0;
    min-inline-size: auto;
  }

  .repos {
    max-height: min(60vh, 360px);
    overflow-y: auto;
  }

  label {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-1) 6px;
    border-radius: 3px;
    font-size: var(--text-sm);
    cursor: pointer;
  }

  label:hover {
    background: var(--surface-hover);
  }

  label span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  input {
    flex: none;
    margin: 0;
    accent-color: var(--accent);
  }

  hr {
    margin: var(--space-1) 0;
    border: 0;
    border-top: 1px solid var(--border);
  }

  .hint {
    margin: 0;
    padding: var(--space-1) 6px 0;
    font-size: var(--text-xs);
    color: var(--text-muted);
  }
</style>
