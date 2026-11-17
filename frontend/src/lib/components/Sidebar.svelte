<!--
  @component
  The page navigation. Collapses into a horizontal tab row on narrow screens.

  Props:
  - `current`: the active page; a gate panel over the Gates page highlights Gates
  - `flakyCount`: flaky gates under the current filters, shown as a badge when above zero
-->
<script lang="ts">
  import { href, type Page } from "../router.svelte";

  interface Props {
    current: Page;
    flakyCount: number | null;
  }

  let { current, flakyCount }: Props = $props();

  const items: { page: Exclude<Page, "gate">; label: string }[] = [
    { page: "overview", label: "Overview" },
    { page: "gates", label: "Gates" },
    { page: "activity", label: "Activity" },
    { page: "flaky", label: "Flaky" },
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
          <span>{item.label}</span>
          {#if item.page === "flaky" && flakyCount}
            <span class="badge">{flakyCount}</span>
          {/if}
        </a>
      </li>
    {/each}
  </ul>
</nav>

<style>
  .sidebar {
    padding: var(--space-2);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }

  a {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    height: var(--row-height);
    padding: 0 var(--space-2);
    border-radius: var(--radius);
    color: var(--text-muted);
    text-decoration: none;
    font-weight: 500;
  }

  a:hover {
    background: var(--surface-hover);
    color: var(--text);
  }

  a[aria-current="page"] {
    background: var(--accent-soft);
    color: var(--text);
    box-shadow: inset 2px 0 0 var(--accent);
  }

  .badge {
    min-width: 18px;
    padding: 0 5px;
    border-radius: 9px;
    background: var(--flaky-soft);
    color: var(--flaky);
    font-size: var(--text-xs);
    font-weight: 600;
    line-height: 16px;
    text-align: center;
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

    a[aria-current="page"] {
      box-shadow: inset 0 -2px 0 var(--accent);
    }
  }
</style>
