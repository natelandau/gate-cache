<script lang="ts">
  import FilterChip from "../lib/components/FilterChip.svelte";
  import { createQuery, type Query } from "../lib/query.svelte";
  import { navigate } from "../lib/router.svelte";
  import { spanLabel, type DaySpan } from "../lib/selection";
  import { loadSummary, type SummaryView } from "../lib/summary";
  import BreakdownModule from "./overview/BreakdownModule.svelte";
  import CalendarModule from "./overview/CalendarModule.svelte";
  import CoalescingModule from "./overview/CoalescingModule.svelte";
  import DailyModule from "./overview/DailyModule.svelte";
  import FailuresModule from "./overview/FailuresModule.svelte";
  import FlakyModule from "./overview/FlakyModule.svelte";
  import HourlyModule from "./overview/HourlyModule.svelte";
  import OutcomeModule from "./overview/OutcomeModule.svelte";
  import ReasonsModule from "./overview/ReasonsModule.svelte";
  import SlowdownsModule from "./overview/SlowdownsModule.svelte";
  import SpentModule from "./overview/SpentModule.svelte";
  import StatsModule from "./overview/StatsModule.svelte";
  import TopGatesModule from "./overview/TopGatesModule.svelte";

  interface Props {
    /** The shell's summary query, shared with the sidebar's flaky badge. */
    query: Query<SummaryView>;
    repoLabel: string | null;
    /** Page-local days picked on the calendar or daily chart, from the hash route. */
    span?: DaySpan;
  }

  let { query, repoLabel, span }: Props = $props();

  // The calendar and the daily charts keep the whole range so other days stay pickable; the
  // stats and outcome mix follow the picked days through their own summary.
  const scoped = createQuery(
    (signal) => (span ? loadSummary(signal, span) : Promise.resolve(undefined)),
    () => span,
  );
  const scopedQuery = $derived(span ? scoped : query);

  let heading: HTMLElement;

  // Picking replaces the history entry, like the Activity filters.
  function pick(next: DaySpan | undefined): void {
    navigate(next ? { page: "overview", span: next } : { page: "overview" }, { replace: true });
  }

  function clear(): void {
    pick(undefined);
    heading.focus();
  }
</script>

<section class="page" aria-labelledby="overview-title">
  <div class="head">
    <h1 id="overview-title" class="page-title" tabindex="-1" bind:this={heading}>Overview</h1>
    {#if span}
      <FilterChip label="Days: {spanLabel(span)}" removeLabel="Show the whole range" onremove={clear} />
    {/if}
  </div>

  <StatsModule query={scopedQuery} {span} days={query.data?.days} />
  <CalendarModule {query} {repoLabel} {span} onselect={pick} />
  <DailyModule {query} {repoLabel} {span} onselect={pick} />
  <SpentModule {repoLabel} {span} onselect={pick} />

  <div class="row halves">
    <HourlyModule {repoLabel} {span} />
    <TopGatesModule {repoLabel} {span} />
  </div>
  <div class="row thirds">
    <OutcomeModule query={scopedQuery} {repoLabel} {span} />
    <FlakyModule {repoLabel} {span} />
    <ReasonsModule {repoLabel} {span} />
  </div>
  <div class="row wide-narrow">
    <FailuresModule {repoLabel} {span} />
    <SlowdownsModule {repoLabel} {span} />
  </div>
  <div class="row wide-narrow">
    <BreakdownModule {repoLabel} {span} />
    <CoalescingModule {repoLabel} {span} />
  </div>
</section>

<style>
  .page {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-4);
  }

  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
  }

  .page-title:focus {
    outline: none;
  }

  .row {
    display: grid;
    gap: var(--space-4);
  }

  .halves {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .thirds {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .wide-narrow {
    grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
  }

  @media (max-width: 900px) {
    .row {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
