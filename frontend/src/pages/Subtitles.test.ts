import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import Activity from "./Activity.svelte";
import Triage from "./Triage.svelte";
import { TRIAGE } from "../lib/terms";

describe("page subtitles", () => {
  it("names the repo filter and the range on Activity", () => {
    const { body } = render(Activity, { props: { repoLabel: "api-server", filter: {} } });
    expect(body).toMatch(/class="subtitle[^"]*">api-server · /);
  });

  it("names the repo filter and the range on Triage", () => {
    const { body } = render(Triage, { props: { repoLabel: null, total: null } });
    expect(body).toMatch(/class="subtitle[^"]*">All repos · /);
    expect(body).toContain(TRIAGE.lede);
  });
});
