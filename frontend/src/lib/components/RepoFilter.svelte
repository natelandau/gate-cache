<!--
  @component
  The repo picker: a native select, so it is keyboard and screen reader friendly everywhere.

  Props:
  - `options`: the repos to offer, each `{ value, label, title? }` where `value` is the git
    common directory and `title` the full path shown on hover
  - `value`: the selected repo, or null for all repos
  - `onchange`: called with the new repo, or null for all repos
-->
<script lang="ts" module>
  export interface RepoOption {
    value: string;
    label: string;
    title?: string;
  }
</script>

<script lang="ts">
  interface Props {
    options: RepoOption[];
    value: string | null;
    onchange: (repo: string | null) => void;
  }

  let { options, value, onchange }: Props = $props();

  const ALL = "";
  // Keep a selected repo listed even when the option list does not include it yet.
  const shown = $derived(
    value !== null && !options.some((o) => o.value === value)
      ? [...options, { value, label: value, title: value }]
      : options,
  );
  const selected = $derived(shown.find((o) => o.value === value));
</script>

<label class="repo" title={selected?.title}>
  <span class="caption">Repository</span>
  <select
    value={value ?? ALL}
    onchange={(event) => {
      const next = event.currentTarget.value;
      onchange(next === ALL ? null : next);
    }}
  >
    <option value={ALL}>All repos</option>
    {#each shown as option (option.value)}
      <option value={option.value} title={option.title}>{option.label}</option>
    {/each}
  </select>
</label>

<style>
  .repo {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }

  .caption {
    flex: none;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  select {
    height: var(--control-height);
    max-width: 240px;
    min-width: 0;
    padding: 0 26px 0 var(--space-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background-color: var(--surface);
    color: var(--text);
    font: inherit;
    font-size: var(--text-sm);
    text-overflow: ellipsis;
    cursor: pointer;
  }

  select:hover {
    border-color: var(--border-strong);
  }
</style>
