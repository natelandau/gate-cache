/** Totals around the weekday by hour heatmap. */

import type { HourCell } from "./api";
import { heatValue, type HeatMetric } from "./heat";

/** Return the metric summed over every weekday, one total per hour of the day. */
export function hourTotals(cells: HourCell[], metric: HeatMetric): number[] {
  const totals = Array<number>(24).fill(0);
  for (const cell of cells) totals[cell.hour]! += heatValue(cell, metric);
  return totals;
}

/** Return the metric summed over every hour, one total per weekday, Sunday first. */
export function weekdayTotals(cells: HourCell[], metric: HeatMetric): number[] {
  const totals = Array<number>(7).fill(0);
  for (const cell of cells) totals[cell.weekday]! += heatValue(cell, metric);
  return totals;
}

/** Return the cell with the largest value, or null when every cell is zero. */
export function peakCell(cells: HourCell[], metric: HeatMetric): HourCell | null {
  let peak: HourCell | null = null;
  for (const cell of cells) {
    if (heatValue(cell, metric) > (peak ? heatValue(peak, metric) : 0)) peak = cell;
  }
  return peak;
}
