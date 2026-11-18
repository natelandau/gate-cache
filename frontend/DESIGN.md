# Dashboard design guide

Read this page before you add or change anything in the dashboard UI. It gives the rules that the code cannot show: which color means what, which component to use, and how a page must behave. The token values live in `src/app.css`. The components live in `src/lib/components/`, and each one documents its props in an `@component` block.

## Principles

The dashboard is an operations tool that people open many times a day. These principles decide most design questions:

- Data comes first. Use dense rows (28px), tabular numbers, and small type. Do not add large cards, hero sections, or decorative motion.
- Freshness and filters are always visible. Every page reads the global date range and the global repo filter, and the top bar shows when the data last updated. Page-local filters, such as the Activity outcome, reason, and Breakdown row and the days picked on the Overview, live only in the hash route. They are not saved, and other pages ignore them. Each one shows as a `FilterChip` that removes it.
- A chart mark or count that stands for a set of runs is a way into those runs. A day on a chart scopes the Overview, and a count links to Activity filtered to exactly those runs. Build the link with `activityHref` in `src/lib/router.svelte.ts`, and keep the day selection logic in `src/lib/selection.ts`.
- Familiar controls win over new ones. Use native `<select>`, radio buttons, and buttons, styled with tokens.
- Every control is reachable with the keyboard and shows a visible focus ring. Motion respects `prefers-reduced-motion`.
- Light and dark themes are equal. Check every change in both. The theme button in the top bar switches between System (the default), Light, and Dark.

## Palette

The app uses six palette colors, defined once as `--palette-100` to `--palette-600`. Each color has one role. Use the color for its role and for nothing else.

| Slot  | Color     | Role                                                                                            | Tokens                                 |
| ----- | --------- | ----------------------------------------------------------------------------------------------- | -------------------------------------- |
| `100` | `#3A93E6` | Brand: favicon, active navigation, accent buttons, links, focus ring, "skip" badge, run counts | `--accent`, `--focus`, `--chart-runs`  |
| `200` | `#BB82E3` | Flaky gates                                                                                     | `--flaky`                              |
| `300` | `#DA637A` | Failures: "fail" badge, failure counts, error notices, the failures chart series                | `--danger`, `--chart-failures`         |
| `400` | `#D98B08` | Warnings: stale data, degraded data                                                             | `--warn`                               |
| `500` | `#70A030` | Success: "pass" badge, the live indicator, time saved                                           | `--ok`, `--chart-saved`                |
| `600` | `#00BBB3` | Passes that gate-cache did not cache                                                            | `--info`                               |

Each role token except `--focus` and the chart tokens has a `-soft` partner, such as `--danger-soft`, for the background behind its text. Gray text, surfaces, and borders use the neutral tokens (`--text`, `--text-muted`, `--surface`, `--border`, and the others in `src/app.css`). Gray chart marks, such as bars for counts that are neither good nor bad, use `--chart-neutral`. Charts that split runs by outcome color each outcome with `--chart-skip`, `--chart-pass`, `--chart-pass-unrecorded`, `--chart-fail`, and `--chart-uncached`, which follow the outcome badge roles and use gray for uncached runs.

A chart that splits runs into ranked parts, such as time spent per gate, colors the parts with `--chart-runs-1` to `--chart-runs-5` in rank order, the most prominent step for the largest part, and uses `--chart-neutral` gray for the rest.

### Heatmap ramps

The heatmaps use one six-step ramp per measure. Step 0 is `--heat-empty` and means no activity. Steps 1 to 5 go from a faint tint to the strongest color, so step 5 always stands out most, in both themes.

| Measure    | Hue                | Tokens                                     |
| ---------- | ------------------ | ------------------------------------------ |
| Runs       | Blue, slot `100`   | `--heat-runs-1` to `--heat-runs-5`         |
| Time saved | Green, slot `500`  | `--heat-saved-1` to `--heat-saved-5`       |
| Failures   | Red, slot `300`    | `--heat-fail-1` to `--heat-fail-5`         |

Get a cell color from `heatStep` and `heatColor` in `src/lib/heat.ts`, not by building the token name in a component. Ramp steps are marks, so they need no text contrast. Never put text on a ramp step.

### Color rules

These rules keep the palette readable and consistent:

1. Never write a hex value or `rgb()` in a component. Use a token from `src/app.css`. If no token fits, add one there with a light value and a dark value. Light values live under `:root`, and dark values live under `:root[data-theme="dark"]`.
2. Use the role token (`--accent`, `--danger`, and so on) for text, icons, and borders. The palette slots are mid-tones, and they are too light for small text on white. The role tokens are darker shades in light mode and lighter shades in dark mode, and each one reaches 4.5:1 contrast on `--bg`, `--surface`, and its `-soft` background.
3. Use a palette slot directly only for chart marks, dots, the favicon, and the focus ring. Time saved is green, runs are blue, and failures are red in every chart, bar, and heatmap.
4. Never show blue (`100`) and violet (`200`) as two series in one chart. Readers with protanopia cannot tell them apart.
5. Never let color carry meaning alone. A badge has a text label, a chart has a legend and a screen-reader table, and a count has a label. A picked chart mark gets an outline or ring, the other marks dim, and `aria-pressed` or `aria-selected` states the pick.
6. If you add a token, follow the derivation rule in the comment at the top of `src/app.css`, then measure the contrast of each new text token in both themes.

## Components

Use an existing component before you write markup of your own. If a page needs a control that no component covers, add a shared component in `src/lib/components/` and use it from the page. Do not style a one-off control inside a page.

| Need                                                  | Component                         |
| ----------------------------------------------------- | --------------------------------- |
| A table of rows, sortable, with optional row clicks   | `DataTable`                       |
| The table of gates on the Gates page                  | `GateTable`                       |
| A row of headline numbers                             | `StatStrip`                       |
| Time saved and failures per day                       | `DailyChart`                      |
| Time spent per day, stacked by gate                   | `SpentChart`                      |
| Run time of one gate over time                        | `TrendChart`                      |
| The outcome of one run                                | `OutcomeBadge`                    |
| Any other short label, such as "flaky"                | `Badge` (pick the tone by role)   |
| A page-local filter that the user can remove          | `FilterChip`                      |
| A labeled choice from a short list, such as a filter  | `Select` (a native `<select>`)    |
| A command                                             | `Button` (`accent` for at most one control per view) |
| A one-line message above page content                 | `Notice` (`info`, `warning`, `error`) |
| A region with no data                                 | `EmptyState`, with copy from `src/lib/scope.ts` |
| A button that opens a popover of choices             | `Dropdown`                        |
| A homepage panel with title, loading, error, empty   | `Module`                          |
| Tabs that pick what a module measures                | `MetricTabs`                      |
| One cell per day over the date range                 | `CalendarHeatmap`                 |
| Activity by weekday and hour                         | `HourHeatmap`                     |
| A numbered top-N list, such as Top gates             | `RankedList`                      |
| The share of each outcome as one stacked bar         | `OutcomeMix`                      |
| The share of each part of another whole, such as how waits ended | `ShareMix`             |
| A bar per named row with numeric columns, such as Breakdown | `BarList`, with rows from `breakdownBars` |
| The repo filter, the date range, and freshness        | `TopBar` (already in the app shell), with `RepoPicker` and `RangePicker` |

## Pages

Every page follows the same pattern:

- Load data with `createQuery` from `src/lib/query.svelte.ts`. The page then refetches when new runs arrive and when a filter changes.
- Show the loading text, an error `Notice`, and an `EmptyState` the same way the existing pages do.
- Name the active filter in empty states, for example "No runs in the last 7 days for api-server."
- Use the hash router in `src/lib/router.svelte.ts` for links, so that the browser back button works.
