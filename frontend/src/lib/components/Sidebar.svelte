<!--
  @component
  The page navigation. Collapses into a horizontal tab row on narrow screens.

  Props:
  - `current`: the active page; a gate panel over the Gates page highlights Gates
  - `flakyCount`: flaky gates under the current filters, shown as a badge when above zero
-->
<script lang="ts">
  import { href, type Page } from "../router.svelte";
  import Badge from "./Badge.svelte";
  import Icon, { type IconName } from "./Icon.svelte";

  interface Props {
    current: Page;
    flakyCount: number | null;
  }

  let { current, flakyCount }: Props = $props();

  const items: { page: Exclude<Page, "gate">; label: string; icon: IconName }[] = [
    { page: "overview", label: "Overview", icon: "layout-dashboard" },
    { page: "gates", label: "Gates", icon: "list-checks" },
    { page: "activity", label: "Activity", icon: "activity" },
    { page: "flaky", label: "Flaky", icon: "triangle-alert" },
  ];

  const active = $derived(current === "gate" ? "gates" : current);
</script>

<nav class="sidebar" aria-label="Pages">
  <ul>
    {#each items as item (item.page)}
      <li>
        <a
          href={href({ page: item.page })}
          aria-current={active === item.page ? "page" : undefined}
        >
          <Icon name={item.icon} />
          <span class="label">{item.label}</span>
          {#if item.page === "flaky" && flakyCount}
            <Badge tone="flaky">{flakyCount}</Badge>
          {/if}
        </a>
      </li>
    {/each}
  </ul>
</nav>

<style>
  .sidebar {
    padding: var(--space-3) 10px;
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  a {
    display: flex;
    align-items: center;
    gap: 10px;
    height: var(--row-height);
    padding: 0 10px;
    border-radius: var(--radius-control);
    color: var(--text-muted);
    text-decoration: none;
    transition:
      background-color var(--dur-fast) var(--ease),
      color var(--dur-fast) var(--ease);
  }

  .label {
    flex: 1;
  }

  a:hover {
    background: var(--surface-hover);
    color: var(--text);
  }

  a[aria-current="page"] {
    background: var(--surface);
    color: var(--text);
    font-weight: 500;
    box-shadow: var(--ring);
  }

  @media (max-width: 720px) {
    .sidebar {
      padding: var(--space-1) var(--space-2);
      overflow-x: auto;
    }

    ul {
      flex-direction: row;
      gap: var(--space-1);
    }

    a {
      white-space: nowrap;
    }
  }
</style>
