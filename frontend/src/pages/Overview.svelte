<script lang="ts">
  import FilterChip from "../lib/components/FilterChip.svelte";
  import PageHeader from "../lib/components/PageHeader.svelte";
  import { rangeLabel } from "../lib/range";
  import { filters } from "../lib/state.svelte";
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

  let heading: HTMLElement | undefined = $state();

  const subtitle = $derived(`${repoLabel ?? "All repos"} · ${rangeLabel(filters.range)}`);

  // Picking replaces the history entry, like the Activity filters.
  function pick(next: DaySpan | undefined): void {
    navigate(next ? { page: "overview", span: next } : { page: "overview" }, { replace: true });
  }

  function clear(): void {
    pick(undefined);
    heading?.focus();
  }
</script>

<section class="page" aria-labelledby="overview-title">
  <PageHeader title="Overview" headingId="overview-title" {subtitle} bind:heading>
    {#if span}
      <FilterChip label="Days: {spanLabel(span)}" removeLabel="Show the whole range" onremove={clear} />
    {/if}
  </PageHeader>

  <StatsModule query={scopedQuery} {span} days={query.data?.days} />

  <div class="grid">
    <div class="s8"><DailyModule {query} {repoLabel} {span} onselect={pick} /></div>
    <div class="s4"><CalendarModule {query} {repoLabel} {span} onselect={pick} /></div>
    <div class="s12"><SpentModule {repoLabel} {span} onselect={pick} /></div>
    <div class="s6"><HourlyModule {repoLabel} {span} /></div>
    <div class="s6"><TopGatesModule {repoLabel} {span} /></div>
    <div class="s4"><OutcomeModule query={scopedQuery} {repoLabel} {span} /></div>
    <div class="s4"><FlakyModule {repoLabel} {span} /></div>
    <div class="s4"><ReasonsModule {repoLabel} {span} /></div>
    <div class="s7"><FailuresModule {repoLabel} {span} /></div>
    <div class="s5"><SlowdownsModule {repoLabel} {span} /></div>
    <div class="s7"><BreakdownModule {repoLabel} {span} /></div>
    <div class="s5"><CoalescingModule {repoLabel} {span} /></div>
  </div>
</section>

<style>
  .page {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-4);
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(12, minmax(0, 1fr));
    gap: var(--space-4);
  }

  /* Each slot stretches its module to the row's height, so cards in a row line up. */
  .grid > div {
    display: grid;
    min-width: 0;
  }

  .s4 {
    grid-column: span 4;
  }

  .s5 {
    grid-column: span 5;
  }

  .s6 {
    grid-column: span 6;
  }

  .s7 {
    grid-column: span 7;
  }

  .s8 {
    grid-column: span 8;
  }

  .s12 {
    grid-column: span 12;
  }

  @media (max-width: 1100px) {
    .s4,
    .s5,
    .s6,
    .s7,
    .s8 {
      grid-column: span 12;
    }
  }
</style>
