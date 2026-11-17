<!--
  @component
  The persistent header: product name, repo filter, range filter, freshness, and the theme switch.

  Props:
  - `repos`, `selectedRepos`, `onReposChange`: passed to RepoPicker
  - `range`, `onRangeChange`: passed to RangePicker
  - `freshness`: the props of Freshness

  The theme switch is the last control. It cycles System, Light, Dark through `cycleTheme`.
-->
<script lang="ts">
  import type { ComponentProps } from "svelte";
  import type { RangeSpec } from "../range";
  import { cycleTheme, theme, themeLabel } from "../theme.svelte";
  import Button from "./Button.svelte";
  import Freshness from "./Freshness.svelte";
  import RangePicker from "./RangePicker.svelte";
  import RepoPicker, { type RepoOption } from "./RepoPicker.svelte";

  interface Props {
    repos: RepoOption[];
    selectedRepos: string[];
    onReposChange: (repos: string[]) => void;
    range: RangeSpec;
    onRangeChange: (range: RangeSpec) => void;
    freshness: ComponentProps<typeof Freshness>;
  }

  let { repos, selectedRepos, onReposChange, range, onRangeChange, freshness }: Props = $props();
</script>

<header class="topbar">
  <a class="brand" href="#/overview">gate-cache <span>stats</span></a>
  <div class="filters" role="group" aria-label="Filters">
    <RangePicker value={range} onchange={onRangeChange} />
    <RepoPicker options={repos} value={selectedRepos} onchange={onReposChange} />
  </div>
  <div class="status">
    <Freshness {...freshness} />
    <Button square onclick={cycleTheme} label={themeLabel(theme.value)} title={themeLabel(theme.value)}>
      <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        {#if theme.value === "system"}
          <circle cx="8" cy="8" r="5.5" />
          <path d="M8 2.5a5.5 5.5 0 0 1 0 11z" fill="currentColor" />
        {:else if theme.value === "light"}
          <circle cx="8" cy="8" r="2.75" />
          <path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1.05 1.05M11.55 11.55l1.05 1.05M3.4 12.6l1.05-1.05M11.55 4.45l1.05-1.05" />
        {:else}
          <path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7z" />
        {/if}
      </svg>
    </Button>
  </div>
</header>

<style>
  .topbar {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    min-height: var(--topbar-height);
    padding: var(--space-1) var(--space-4);
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    flex-wrap: wrap;
  }

  .brand {
    width: calc(var(--sidebar-width) - var(--space-4));
    flex: none;
    color: var(--text);
    font-weight: 600;
    text-decoration: none;
    font-family: var(--font-mono);
    font-size: var(--text-md);
  }

  .brand span {
    color: var(--text-faint);
    font-weight: 400;
  }

  .filters {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex-wrap: wrap;
    min-width: 0;
  }

  .status {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin-left: auto;
  }

  @media (max-width: 720px) {
    .topbar {
      gap: var(--space-2);
      padding: var(--space-2) var(--space-3);
    }

    .brand {
      width: auto;
    }
  }
</style>
