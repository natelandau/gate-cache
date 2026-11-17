<script lang="ts">
  import type { Query } from "../lib/query.svelte";
  import type { SummaryView } from "../lib/summary";
  import CalendarModule from "./overview/CalendarModule.svelte";
  import CoalescingModule from "./overview/CoalescingModule.svelte";
  import DailyModule from "./overview/DailyModule.svelte";
  import FailuresModule from "./overview/FailuresModule.svelte";
  import FlakyModule from "./overview/FlakyModule.svelte";
  import HourlyModule from "./overview/HourlyModule.svelte";
  import OutcomeModule from "./overview/OutcomeModule.svelte";
  import ReasonsModule from "./overview/ReasonsModule.svelte";
  import ReposModule from "./overview/ReposModule.svelte";
  import SlowdownsModule from "./overview/SlowdownsModule.svelte";
  import StatsModule from "./overview/StatsModule.svelte";
  import TopGatesModule from "./overview/TopGatesModule.svelte";

  interface Props {
    /** The shell's summary query, shared with the sidebar's flaky badge. */
    query: Query<SummaryView>;
    repoLabel: string | null;
  }

  let { query, repoLabel }: Props = $props();
</script>

<section class="page" aria-labelledby="overview-title">
  <h1 id="overview-title" class="page-title">Overview</h1>

  <StatsModule {query} />
  <CalendarModule {query} {repoLabel} />
  <DailyModule {query} {repoLabel} />

  <div class="row halves">
    <HourlyModule {repoLabel} />
    <TopGatesModule {repoLabel} />
  </div>
  <div class="row thirds">
    <OutcomeModule {query} {repoLabel} />
    <FlakyModule {repoLabel} />
    <ReasonsModule {repoLabel} />
  </div>
  <div class="row wide-narrow">
    <FailuresModule {repoLabel} />
    <SlowdownsModule {repoLabel} />
  </div>
  <div class="row wide-narrow">
    <ReposModule />
    <CoalescingModule {repoLabel} />
  </div>
</section>

<style>
  .page {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-4);
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
