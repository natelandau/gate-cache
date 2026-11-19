import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import Activity from "./Activity.svelte";
import Flaky, { FLAKY_LEDE } from "./Flaky.svelte";

describe("page subtitles", () => {
  it("names the repo filter and the range on Activity", () => {
    const { body } = render(Activity, { props: { repoLabel: "api-server", filter: {} } });
    expect(body).toMatch(/class="subtitle[^"]*">api-server · /);
  });

  it("names the repo filter and the range on Flaky, and keeps its definition", () => {
    const { body } = render(Flaky, { props: { repoLabel: null } });
    expect(body).toMatch(/class="subtitle[^"]*">All repos · /);
    expect(body).toContain(FLAKY_LEDE);
  });
});
