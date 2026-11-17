import { svelte } from "@sveltejs/vite-plugin-svelte";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

/**
 * Lazy layerchart features the dashboard never turns on, as [importing file, import specifier].
 * Each still emits a chunk that ships in the wheel, so the build swaps it for a stub that fails
 * loudly. To use one of these features, delete its entry here.
 */
const UNUSED_LAYERCHART_IMPORTS: [importer: string, specifier: string][] = [
  // Voronoi and radial tooltip modes.
  ["components/tooltip/TooltipContext.svelte", "../Voronoi/Voronoi.svelte"],
  ["components/tooltip/TooltipContext.svelte", "../Arc/Arc.svelte"],
  // Zoom/pan and brushing.
  ["components/Chart/Chart.base.svelte", "../TransformContext.svelte"],
  ["components/Chart/Chart.base.svelte", "../BrushContext.svelte"],
  // The `annotations` chart prop.
  ["components/ChartChildren/ChartChildren.base.svelte", "../charts/ChartAnnotations.svelte"],
];

const STUB_PREFIX = "\0layerchart-unused:";

function stubUnusedLayerchart(): Plugin {
  const matched = new Set<number>();
  let building = false;
  return {
    name: "stub-unused-layerchart",
    enforce: "pre",
    configResolved(config) {
      building = config.command === "build";
    },
    buildStart() {
      matched.clear();
    },
    resolveId(source, importer) {
      if (!importer?.includes("/node_modules/layerchart/")) return null;
      const index = UNUSED_LAYERCHART_IMPORTS.findIndex(
        ([file, specifier]) => importer.endsWith(file) && source === specifier,
      );
      if (index === -1) return null;
      matched.add(index);
      // The .js suffix keeps the Svelte compiler from treating the stub as a component source.
      return `${STUB_PREFIX}${source}.js`;
    },
    buildEnd(error) {
      // A dev server or test run loads only some modules, so only a full build proves an entry.
      if (!building || error) return;
      const stale = UNUSED_LAYERCHART_IMPORTS.filter((_, index) => !matched.has(index));
      if (stale.length > 0) {
        const list = stale.map(([file, specifier]) => `${file} -> ${specifier}`).join(", ");
        this.error(`layerchart stub entries matched no import, so update them: ${list}`);
      }
    },
    load(id) {
      if (!id.startsWith(STUB_PREFIX)) return null;
      const name = JSON.stringify(id.slice(STUB_PREFIX.length, -".js".length));
      return `export default function unusedLayerchartModule() {
  throw new Error("layerchart module " + ${name} + " is stubbed out in vite.config.ts");
}`;
    },
  };
}

export default defineConfig({
  plugins: [stubUnusedLayerchart(), svelte()],
  // The server always mounts the app at the root, so absolute asset URLs also load on deep paths.
  base: "/",
  build: {
    // The server caches everything under assets/ as immutable, so every file name there needs a hash.
    outDir: "../src/gate_cache/dashboard/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      // The dashboard rejects any Host but its own, so rewrite it to the target's.
      "/api": { target: "http://127.0.0.1:7879", changeOrigin: true },
    },
  },
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
    // A zone with daylight saving time, so tests of local day boundaries are deterministic.
    env: { TZ: "America/New_York" },
  },
});
