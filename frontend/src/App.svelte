<script lang="ts">
  import { onMount } from "svelte";
  import { getFreshness, getRepos } from "./lib/api";
  import Notice from "./lib/components/Notice.svelte";
  import Sidebar from "./lib/components/Sidebar.svelte";
  import TopBar from "./lib/components/TopBar.svelte";
  import { createQuery } from "./lib/query.svelte";
  import { repoOptions, repoSelectionLabel } from "./lib/repos";
  import { loadSummary } from "./lib/summary";
  import { closeGatePanel } from "./lib/panel";
  import { panelHost, router, startRouter } from "./lib/router.svelte";
  import type { DaySpan } from "./lib/selection";
  import {
    clock,
    filters,
    freshness,
    setRange,
    setRepos,
    startClock,
    startFreshnessPolling,
    timeZone,
  } from "./lib/state.svelte";
  import Activity from "./pages/Activity.svelte";
  import Flaky from "./pages/Flaky.svelte";
  import GateDetail from "./pages/GateDetail.svelte";
  import Gates from "./pages/Gates.svelte";
  import Overview from "./pages/Overview.svelte";

  onMount(() => {
    const stops = [
      startRouter(),
      startClock(),
      startFreshnessPolling((signal) => getFreshness({ signal })),
    ];
    return () => stops.forEach((stop) => stop());
  });

  // Every repo ever recorded, so the picker does not shrink with the filters it controls.
  const repos = createQuery(
    (signal) => getRepos({ signal, scope: { repos: [], tz: timeZone() } }),
    undefined,
    { repos: false, range: false },
  );

  // One summary feeds both the Overview page and the flaky badge, which follows the filters.
  const summary = createQuery(loadSummary);

  const options = $derived(repoOptions(repos.data ?? []));
  const selectedRepo = $derived(repoSelectionLabel(filters.repos, options));

  const titles = {
    overview: "Overview",
    gates: "Gates",
    gate: "Gate",
    activity: "Activity",
    flaky: "Flaky",
  } as const;

  const page = $derived(router.route.page);
  const openGate = $derived(
    router.route.page === "gate" ? { repo: router.route.repo, name: router.route.name } : null,
  );
  const host = $derived(panelHost(router.route, router.opener));
  // A gate panel over the overview keeps the days the overview was scoped to. Every hash
  // change parses a new span object, so the span is rebuilt only when its days change, and
  // the overview does not reload for the same days.
  const spanKey = $derived.by(() => {
    const span =
      router.route.page === "overview"
        ? router.route.span
        : router.opener?.page === "overview"
          ? router.opener.span
          : undefined;
    return span ? `${span.from}/${span.to}` : "";
  });
  const overviewSpan = $derived.by<DaySpan | undefined>(() => {
    const [from, to] = spanKey.split("/");
    return from && to ? { from, to } : undefined;
  });
  // A gate opened from the overview stays over it, so the sidebar keeps Overview active.
  const navPage = $derived(host === "overview" ? "overview" : page);
  const pageTitle = $derived(
    router.route.page === "gate" ? router.route.name : titles[router.route.page],
  );

  $effect(() => {
    document.title = `${pageTitle} · gate-cache`;
  });

  let main: HTMLElement;
  let topHeight = $state(0);
</script>

<!-- A button, not a #main link, because the hash belongs to the router. -->
<button class="skip" type="button" onclick={() => main.focus()}>Skip to content</button>
<!-- Panels below the sticky top bar read its live height, which grows when controls wrap. -->
<div class="shell" style:--topbar-offset={topHeight ? `${topHeight}px` : undefined}>
  <div class="top" bind:offsetHeight={topHeight}>
    <TopBar
      repos={options}
      selectedRepos={filters.repos}
      onReposChange={setRepos}
      range={filters.range}
      onRangeChange={setRange}
      freshness={{
        stale: freshness.stale,
        updatedAt: freshness.updatedAt,
        now: clock.now,
        ingestError: freshness.ingestError,
        lastIngest: freshness.lastIngest,
      }}
    />
  </div>
  <div class="body">
    <aside class="nav">
      <Sidebar current={navPage} flakyCount={summary.data?.summary.flaky_gates ?? null} />
    </aside>
    <main bind:this={main} tabindex="-1">
      {#if freshness.recording === false}
        <Notice>Recording is off. Run <code>gate-cache stats on</code> to start.</Notice>
      {/if}
      {#if freshness.ingestError && !freshness.stale}
        <Notice tone="warning">
          New events are not being ingested: {freshness.ingestError}. The numbers below may be
          behind.
        </Notice>
      {/if}
      {#if freshness.stale}
        <Notice tone="warning">
          The dashboard server is not responding. Showing the last data received.
        </Notice>
      {/if}
      <!-- One branch for the overview with or without its gate panel, so closing the panel
           keeps the page mounted with its tabs, scroll, and data. -->
      {#if page === "overview" || host === "overview"}
        <Overview query={summary} repoLabel={selectedRepo} span={overviewSpan} />
        {#if host === "overview" && openGate}
          <GateDetail
            repo={openGate.repo}
            name={openGate.name}
            onclose={() => closeGatePanel(null, { page: "overview" })}
          />
        {/if}
      {:else if page === "gates" || page === "gate"}
        <Gates open={openGate} repoLabel={selectedRepo} />
      {:else if router.route.page === "activity"}
        {@const { page: _, ...filter } = router.route}
        <Activity repoLabel={selectedRepo} {filter} />
      {:else}
        <Flaky repoLabel={selectedRepo} />
      {/if}
    </main>
  </div>
</div>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }

  /* Filters and freshness stay in view over long tables and under the gate panel. */
  .top {
    position: sticky;
    top: 0;
    z-index: 6;
  }

  .body {
    flex: 1;
    display: grid;
    grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  }

  .nav {
    border-right: 1px solid var(--border);
  }

  main {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-5) 28px var(--space-6);
    max-width: var(--content-max);
    width: 100%;
  }

  main:focus {
    outline: none;
  }

  .skip {
    position: absolute;
    left: var(--space-2);
    top: -40px;
    z-index: 10;
    padding: var(--space-1) var(--space-2);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    font: inherit;
  }

  .skip:focus {
    top: var(--space-2);
  }

  @media (max-width: 720px) {
    .body {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: auto 1fr;
    }

    .nav {
      border-right: 0;
      border-bottom: 1px solid var(--border);
    }

    main {
      padding: var(--space-3) var(--space-4);
    }
  }
</style>
