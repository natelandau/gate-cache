<script lang="ts">
  import { onMount } from "svelte";
  import { getFreshness, getRepos } from "./lib/api";
  import Notice from "./lib/components/Notice.svelte";
  import Sidebar from "./lib/components/Sidebar.svelte";
  import TopBar from "./lib/components/TopBar.svelte";
  import { createQuery } from "./lib/query.svelte";
  import { repoLabel, repoOptions } from "./lib/repos";
  import { loadSummary } from "./lib/summary";
  import { repoPageRepo, router, startRouter } from "./lib/router.svelte";
  import {
    clock,
    filters,
    freshness,
    setRange,
    setRepo,
    startClock,
    startFreshnessPolling,
    timeZone,
  } from "./lib/state.svelte";
  import Activity from "./pages/Activity.svelte";
  import Flaky from "./pages/Flaky.svelte";
  import Gates from "./pages/Gates.svelte";
  import Overview from "./pages/Overview.svelte";
  import RepoDetail from "./pages/RepoDetail.svelte";
  import Repos from "./pages/Repos.svelte";

  onMount(() => {
    const stops = [
      startRouter(),
      startClock(),
      startFreshnessPolling((signal) => getFreshness({ signal })),
    ];
    return () => stops.forEach((stop) => stop());
  });

  // Every repo ever recorded, so the picker does not shrink with the filters it controls.
  const repos = createQuery((signal) => getRepos({ signal, scope: { repo: null, tz: timeZone() } }));

  // One summary feeds both the Overview page and the flaky badge, which follows the filters.
  const summary = createQuery(loadSummary);

  const options = $derived(repoOptions(repos.data ?? []));
  const selectedRepo = $derived(repoLabel(filters.repo, options));

  const titles = {
    overview: "Overview",
    gates: "Gates",
    gate: "Gate",
    repos: "Repos",
    repo: "Repo",
    activity: "Activity",
    flaky: "Flaky",
  } as const;

  const page = $derived(router.route.page);
  const openGate = $derived(
    router.route.page === "gate" ? { repo: router.route.repo, name: router.route.name } : null,
  );
  // A gate opened from a repo page keeps that page mounted under the panel, so closing the
  // panel returns to it without a reload and can focus the gate's row.
  const detailRepo = $derived(repoPageRepo(router.route, router.opener));
  const detailLabel = $derived(detailRepo === null ? null : repoLabel(detailRepo, options));
  const pageTitle = $derived.by(() => {
    if (router.route.page === "gate") return router.route.name;
    if (detailLabel !== null) return detailLabel;
    return titles[router.route.page];
  });

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
      repo={filters.repo}
      onRepoChange={setRepo}
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
      <Sidebar current={detailRepo === null ? page : "repo"} flakyCount={summary.data?.summary.flaky_gates ?? null} />
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
      {#if detailRepo !== null}
        <!-- Remount per repo so a new repo shows Loading, not the previous repo's numbers. -->
        {#key detailRepo}
          <RepoDetail repo={detailRepo} label={detailLabel ?? detailRepo} open={openGate} />
        {/key}
      {:else if page === "overview"}
        <Overview query={summary} repoLabel={selectedRepo} />
      {:else if page === "gates" || page === "gate"}
        <Gates open={openGate} repoLabel={selectedRepo} />
      {:else if page === "repos"}
        <Repos repoLabel={selectedRepo} />
      {:else if page === "activity"}
        <Activity repoLabel={selectedRepo} />
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
    background: var(--surface);
  }

  main {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-5);
    max-width: 1280px;
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
