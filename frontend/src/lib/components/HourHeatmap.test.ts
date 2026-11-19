import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import HourHeatmap from "./HourHeatmap.svelte";

const cells = [
  { weekday: 1, hour: 9, runs: 8, saved: 30, failures: 0 },
  { weekday: 3, hour: 14, runs: 2, saved: 5, failures: 4 },
];

describe("HourHeatmap", () => {
  it("draws a 7 by 24 grid on the metric's ramp", () => {
    const { body } = render(HourHeatmap, { props: { cells, metric: "fail" } });
    const styles = [...body.matchAll(/class="cell[ "][^>]*style="background: ([^;"]+)/g)].map(
      (m) => m[1],
    );
    expect(styles).toHaveLength(168);
    expect(styles[3 * 24 + 14]).toBe("var(--heat-fail-5)");
    expect(styles[1 * 24 + 9]).toBe("var(--heat-empty)");
  });

  it("shows a total bar per hour and a total per weekday", () => {
    const { body } = render(HourHeatmap, { props: { cells, metric: "runs" } });
    expect(body.match(/class="hour-total[^"]*"/g)).toHaveLength(24);
    expect(body.match(/class="day-total[^"]*"/g)).toHaveLength(7);
    expect(body).toMatch(/class="day-total[^"]*"[\s\S]*?>8</);
  });

  it("names the peak hour", () => {
    const { body } = render(HourHeatmap, { props: { cells, metric: "runs" } });
    expect(body).toMatch(/Peak:[\s\S]*?09:00[\s\S]*?8/);
  });

  it("labels every third hour", () => {
    const { body } = render(HourHeatmap, { props: { cells, metric: "runs" } });
    const labels = [...body.matchAll(/class="hour[^"]*"[^>]*>(\d*)</g)].map((m) => m[1]).filter(Boolean);
    expect(labels).toEqual(["0", "3", "6", "9", "12", "15", "18", "21"]);
  });

  it("has a screen-reader table of weekday by hour", () => {
    const { body } = render(HourHeatmap, { props: { cells, metric: "runs" } });
    expect(body.match(/<th scope="row">/g)?.length).toBe(7);
    expect(body.match(/<th scope="col">/g)?.length).toBe(25);
  });
});
