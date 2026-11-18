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
  import Icon from "./Icon.svelte";
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
  <a class="brand" href="#/overview"><span class="mark"><Icon name="check-check" size={14} /></span>gate-cache</a>
  <div class="filters" role="group" aria-label="Filters">
    <RangePicker value={range} onchange={onRangeChange} />
    <RepoPicker options={repos} value={selectedRepos} onchange={onReposChange} />
  </div>
  <div class="status">
    <Freshness {...freshness} />
    <Button square onclick={cycleTheme} label={themeLabel(theme.value)} title={themeLabel(theme.value)}>
      <Icon name={theme.value === "system" ? "sun-moon" : theme.value === "light" ? "sun" : "moon"} />
    </Button>
  </div>
</header>

<style>
  .topbar {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    min-height: var(--topbar-height);
    padding: var(--space-2) var(--space-4);
    border-bottom: 1px solid var(--border);
    background: var(--bg);
    flex-wrap: wrap;
  }

  .brand {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    width: calc(var(--sidebar-width) - var(--space-4));
    flex: none;
    color: var(--text);
    font-size: 15px;
    font-weight: 600;
    letter-spacing: -0.02em;
    text-decoration: none;
  }

  .mark {
    display: grid;
    place-items: center;
    width: 22px;
    height: 22px;
    border-radius: var(--radius-control);
    background: var(--text);
    color: var(--bg);
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
