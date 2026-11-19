import { describe, expect, it, vi } from "vitest";
import type { ActivityFilter } from "../lib/api";
import { OUTCOMES } from "../lib/events";
import { gateChoices, outcomeChoices, withList, withToggle } from "../lib/filtermenu";
import { html } from "../lib/render.test-utils";
import { href, parseHash } from "../lib/router.svelte";
import { ACTIVITY_FILTERS } from "../lib/terms";
import Activity from "./Activity.svelte";

vi.mock("../lib/query.svelte", () => ({
  createQuery: () => ({ data: undefined, error: undefined, loading: true }),
}));

const lint = { repo: "/a/.git", repo_name: "a", name: "lint" };

describe("Filter menu wiring", () => {
  it("puts values picked by hand in the hash, where they read back as chips on the page", () => {
    const outcomes = outcomeChoices().filter((c) => c.value === "fail" || c.value === "skip");
    const gates = gateChoices([lint, { ...lint, name: "test" }]);
    let filter = withList({}, "outcome", outcomes.map((c) => c.item));
    filter = withList(filter, "gate", gates.map((c) => c.item));
    filter = withToggle(filter, "spotCheck", true);

    const { page: _, ...parsed } = parseHash(href({ page: "activity", ...filter })) as { page: "activity" } & ActivityFilter;
    expect(parsed).toEqual(filter);

    const body = html(Activity, { props: { repoLabel: null, filter: parsed } });
    for (const chip of [
      ACTIVITY_FILTERS.chip(ACTIVITY_FILTERS.outcome, [OUTCOMES.skip.label, OUTCOMES.fail.label]),
      ACTIVITY_FILTERS.chip(ACTIVITY_FILTERS.gate, ["lint", "test"]),
      ACTIVITY_FILTERS.spotCheckChip,
      ACTIVITY_FILTERS.clearAll,
    ]) {
      expect(body).toContain(chip);
    }
  });
});
