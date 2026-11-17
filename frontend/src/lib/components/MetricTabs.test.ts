import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import MetricTabs from "./MetricTabs.svelte";

const options = [
  { value: "runs", label: "Runs" },
  { value: "saved", label: "Time saved" },
];

describe("MetricTabs", () => {
  it("renders a labeled radio group with the value checked", () => {
    const { body } = render(MetricTabs, {
      props: { label: "Activity metric", options, value: "saved", onchange: () => {} },
    });
    expect(body).toMatch(/<legend[^>]*>Activity metric<\/legend>/);
    expect(body).toMatch(/<input type="radio"[^>]*value="saved"[^>]*checked/);
    expect(body).not.toMatch(/<input type="radio"[^>]*value="runs"[^>]*checked/);
    expect(body).toContain("Time saved");
  });
});
