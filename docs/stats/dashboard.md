---
icon: lucide/layout-dashboard
---

# The dashboard

The dashboard shows the runs that gate-cache recorded. Run `gate-cache dashboard` to open it. It updates while it runs, so new runs appear within seconds.

## Pick what to see

The bar at the top applies to every page:

- **Time range.** Pick a relative range, such as 7 days, a calendar period, such as This week, or custom dates.
- **Repositories.** Show one repository, several, or all of them.

Each number on the overview shows its change against the previous period of the same length.

## Overview

![The overview page, with stat cards, a chart of time spent per gate, and a calendar of activity](../images/dashboard-overview.png)

The overview answers "how are my checks doing?":

- **Stat cards:** gate runs, time that gates ran, failures, flaky gates, how often gates skip, and the time that the cache saved.
- **Time gates ran:** run time per day, split into the gates that took the most time.
- **Activity and daily charts:** when gates run, and how many fail. Click a day to scope the page to it, or drag across days to pick a range.
- **Recent failures** and **Gates getting slower.**
- **Top gates:** the gates that ran the longest, saved the most, ran the most, or failed the most.
- **Breakdown:** runs grouped by repository, gate, source, branch, or computer. The source is what started a run: a git hook, CI, a terminal, or a coding agent.

Click a count to see the runs behind it on the Activity page.

## Gates

![The Gates page, a table of gates with their run counts, run times, and time saved](../images/dashboard-gates.png)

One row for each gate, with its runs, how often it skips, its run times, CPU use, peak memory, and the time that it ran and saved. Click a column header to sort by it. Click a gate to open its details.

## Gate details

![The details of one gate, with stat cards, a chart of passing run times, and a histogram of run times](../images/dashboard-gate-detail.png)

The details of a gate show its run time over time, the spread of its run times, its failures, and which sources ran it.

## Activity

A list of runs, newest first. Filter it by outcome, such as failures or skips.

## Flaky

![The Flaky page, a list of hashes with which one gate both failed and passed](../images/dashboard-flaky.png)

Each gate that both failed and passed with the same hash. Read [Find flaky gates](flaky-gates.md).

## Theme

The button at the top right switches between the theme of your system, light, and dark.

![The dashboard overview in the dark theme](../images/dashboard-overview-dark.png)
