import { describe, expect, it } from "vitest";

// Vitest replaces imported CSS with an empty module, so read the file from disk. The
// project has no Node type definitions, hence the computed specifier and the cast.
const fs = (await import(/* @vite-ignore */ ["node", "fs"].join(":"))) as {
  readFileSync(path: URL, encoding: "utf8"): string;
};
const css = fs.readFileSync(new URL("./app.css", import.meta.url), "utf8");

function block(selector: string): string {
  const start = css.indexOf(`${selector} {`);
  return start < 0 ? "" : css.slice(start, css.indexOf("\n}", start));
}

describe("app.css tokens", () => {
  it("loads Geist from the pinned jsDelivr file", () => {
    expect(css).toContain(
      'url("https://cdn.jsdelivr.net/npm/@fontsource-variable/geist@5.2.5/files/geist-latin-wght-normal.woff2")',
    );
  });

  it("falls back to the system font when Geist cannot load", () => {
    const stack = /--font-sans:\s*([^;]+);/.exec(css)?.[1] ?? "";
    expect(stack.startsWith('"Geist"')).toBe(true);
    expect(stack).toContain("system-ui");
  });

  it("defines five gate series colors in both themes", () => {
    for (const selector of [":root", ':root[data-theme="dark"]']) {
      for (let i = 1; i <= 5; i++) expect(block(selector)).toContain(`--chart-series-${i}:`);
    }
    expect(css).not.toContain("--chart-runs-1");
  });

  it("uses no uppercase labels and no monospace UI font", () => {
    expect(css).not.toContain("text-transform: uppercase");
    expect(css).not.toContain("--font-mono");
  });

  it("keeps no keyframes that nothing uses", () => {
    expect(css).not.toContain("@keyframes value-swap");
  });
});
