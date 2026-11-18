import { describe, expect, it } from "vitest";
import { html } from "../render.test-utils";
import OutcomeMix from "./OutcomeMix.svelte";

const counts = { skip: 6, pass: 3, pass_unrecorded: 0, fail: 1, uncached: 0 };

describe("OutcomeMix", () => {
  it("draws one hidden bar segment per nonzero outcome in its color", () => {
    const body = html(OutcomeMix, { props: { counts } });
    expect(body).toMatch(/class="bar[^"]*"[^>]*aria-hidden="true"/);
    const segments = [...body.matchAll(/class="segment[^"]*"[^>]*style="([^"]+)"/g)].map((m) => m[1]);
    expect(segments).toHaveLength(3);
    expect(segments[0]).toContain("background: var(--chart-skip)");
    expect(segments[0]).toContain("width: 60%");
    expect(segments[2]).toContain("background: var(--chart-fail)");
  });

  it("lists every outcome with its label, count, and percent for screen readers too", () => {
    const body = html(OutcomeMix, { props: { counts } });
    expect(body.match(/<li/g)).toHaveLength(5);
    expect(body).toContain("Pass, not cached");
    expect(body).toMatch(/Skip<\/span>\s*<span[^>]*>6<\/span>\s*<span[^>]*>60%</);
    expect(body).not.toMatch(/<ul[^>]*aria-hidden/);
  });

  it("links each non-zero count to its runs", () => {
    const body = html(OutcomeMix, { props: { counts, href: (o: string) => `#/activity?outcome=${o}` } });
    expect(body).toMatch(/<a[^>]*href="#\/activity\?outcome=skip"[^>]*>6<\/a>/);
    expect(body).toMatch(/<a[^>]*href="#\/activity\?outcome=fail"/);
    expect(body).not.toContain('href="#/activity?outcome=uncached"');
  });
});
