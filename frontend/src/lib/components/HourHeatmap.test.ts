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

  it("stays static without links", () => {
    const { body } = render(HourHeatmap, { props: { cells, metric: "runs" } });
    expect(body).not.toContain("<a ");
  });

  it("links every cell with runs, with one tab stop and a spoken name", () => {
    const { body } = render(HourHeatmap, {
      props: { cells, metric: "runs", href: (w: number, h: number) => `#/activity?weekday=${w}&hour=${h}` },
    });
    expect(body.match(/<a /g)?.length).toBe(2);
    expect(body.match(/tabindex="0"/g)?.length).toBe(1);
    expect(body).toContain('href="#/activity?weekday=1&amp;hour=9"');
    const monday = new Date(1970, 0, 5).toLocaleString(undefined, { weekday: "long" });
    expect(body).toContain(`aria-label="${monday} 09:00, Runs: 8. Open in Activity"`);
  });

  it("links only the cells whose shown value is not zero", () => {
    const { body } = render(HourHeatmap, {
      props: { cells, metric: "fail", href: (w: number, h: number) => `#/activity?weekday=${w}&hour=${h}` },
    });
    expect(body.match(/<a /g)?.length).toBe(1);
    expect(body).toContain('href="#/activity?weekday=3&amp;hour=14"');
  });
});
