import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import RangePicker, { presetSpec } from "./RangePicker.svelte";

function applyButton(body: string): string {
  const match = /<button[^>]*>\s*Apply\s*<\/button>/.exec(body);
  if (!match) throw new Error("no Apply button");
  return match[0];
}

describe("RangePicker", () => {
  it("disables Apply when the custom start is after the end", () => {
    const value = { kind: "custom", start: "2020-03-10", end: "2020-03-01" } as const;
    const { body } = render(RangePicker, { props: { value, onchange: () => {} } });
    expect(applyButton(body)).toMatch(/\sdisabled/);
  });

  it("enables Apply for a custom range in order", () => {
    const value = { kind: "custom", start: "2020-03-01", end: "2020-03-10" } as const;
    const { body } = render(RangePicker, { props: { value, onchange: () => {} } });
    expect(applyButton(body)).not.toMatch(/\sdisabled/);
  });

  it("selects the 30d preset as a preset range", () => {
    expect(presetSpec("30d")).toEqual({ kind: "preset", preset: "30d" });
  });

  it("shows the range label and checks the active preset", () => {
    const { body } = render(RangePicker, {
      props: { value: { kind: "preset", preset: "30d" }, onchange: () => {} },
    });
    expect(body).toContain("Last 30 days");
    expect(body).toMatch(/<input type="radio"[^>]*value="30d"[^>]*checked/);
    expect(body).not.toMatch(/<input type="radio"[^>]*value="7d"[^>]*checked/);
  });
});
