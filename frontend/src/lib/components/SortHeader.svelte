<!--
  @component
  A table header button that sorts by its column, with an arrow on the sorted column. A
  right-aligned header puts the arrow on the left, so the label lines up with the numbers below.

  Props:
  - `label`: the column name
  - `direction`: the sort direction when this column is sorted, or null when it is not
  - `align`: "left" or "right" (default "left")
  - `onclick`: called when the header is clicked
-->
<script lang="ts">
  import type { SortDirection } from "../table";
  import Icon from "./Icon.svelte";

  interface Props {
    label: string;
    direction: SortDirection | null;
    align?: "left" | "right";
    onclick: () => void;
    /** Id of an element that explains the column, such as an InfoTip explanation. */
    describedby?: string;
  }

  let { label, direction, align = "left", onclick, describedby }: Props = $props();
</script>

<button type="button" class="sort {align}" class:on={direction !== null} aria-describedby={describedby} {onclick}>
  <span class:explained={!!describedby}>{label}</span>
  <span class="arrow"
    >{#if direction}<Icon name={direction === "asc" ? "arrow-up" : "arrow-down"} size={12} />{/if}</span
  >
</button>

<style>
  .sort {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    height: 22px;
    margin: 0 -4px;
    padding: 0 4px;
    border: 0;
    border-radius: 3px;
    background: none;
    color: inherit;
    font: inherit;
    white-space: nowrap;
    cursor: pointer;
    transition: color var(--dur-fast) var(--ease);
  }

  .right {
    flex-direction: row-reverse;
  }

  .sort:hover,
  .on {
    color: var(--text);
  }

  .arrow {
    display: inline-flex;
    width: 12px;
  }
</style>
