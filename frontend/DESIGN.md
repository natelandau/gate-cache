# Dashboard design guide

Read this page before you add or change anything in the dashboard UI. It gives the rules that the code cannot show: which token to use, which color means what, which component to use, and how a page must behave. The token values live in `src/app.css`. The components live in `src/lib/components/`, and each one documents its props in an `@component` block.

## Principles

The dashboard shows how the user's gates are doing (what runs, how long it takes, and what fails), and what gate-cache saved comes second, so lead every page, default, and sort with the gates' own numbers.

The dashboard is an operations tool that people open many times a day. These principles decide most design questions:

- Data comes first. Every card earns its space with a number, a chart, or a table. Do not add hero sections or decorative images.
- One typeface. Every string is Geist, with tabular figures for numbers. Do not use a monospace face, not even for tree hashes, durations, or commands. One table column never mixes faces.
- Freshness and filters are always visible. Every page reads the global date range and the global repo filter, and the top bar shows when the data last updated. Page-local filters, such as the Activity outcome, reason, and Breakdown row and the days picked on the Overview, live only in the hash route. They are not saved, and other pages ignore them. Each one shows as a `FilterChip` that removes it.
- A chart mark or count that stands for a set of runs is a way into those runs. A day on a chart scopes the Overview, and a count links to Activity filtered to exactly those runs. Build the link with `activityHref` in `src/lib/router.svelte.ts`, and keep the day selection logic in `src/lib/selection.ts`.
- Familiar controls win over new ones. Use native `<select>`, radio buttons, and buttons, styled with tokens.
- Every control is reachable with the keyboard and shows a visible focus ring.
- Light and dark themes are equal. Check every change in both. The theme button in the top bar switches between System (the default), Light, and Dark.

## Content Security Policy

The server sends the policy in `CONTENT_SECURITY_POLICY` in `src/gate_cache/dashboard/server.py`. It allows every script, style, image, and API call from the dashboard's own origin, and fonts from that origin and `https://cdn.jsdelivr.net`. A server test asserts the exact string.

These break silently in the browser, and the frontend tests do not catch them:

- An inline `<script>`. Put a script that must run before paint in `frontend/public/`, like `theme.js`.
- A static `style="..."` attribute in a Svelte template. Svelte `style:` directives and `style={...}` are fine, because they set styles through the CSSOM.
- A `data:` or `blob:` URL, including a gradient or an icon as a data URL. Draw gradients with SVG `<linearGradient>` or CSS.
- A web font or a stylesheet from any host other than the pinned jsDelivr font file.
- A web worker.

The one font file is `@fontsource-variable/geist@5.2.5/files/geist-latin-wght-normal.woff2` on jsDelivr, declared with `@font-face` in `src/app.css`. If the browser cannot reach jsDelivr, text falls back to the system UI font, and the layout stays the same. To change the Geist version, change the URL in `src/app.css` and in the test in `src/app.css.test.ts`.

## Type

Use the type tokens, never a pixel size in a component. Weights are 400, 500, and 600 only. Labels and titles are sentence case. Do not uppercase any text.

| Token             | Size / line height | Weight   | Tracking                   | Use                                                       |
| ----------------- | ------------------ | -------- | -------------------------- | --------------------------------------------------------- |
| `--text-xs`       | 12 / 16            | 400, 500 | 0                          | Labels, axis ticks, chips, table headers, hints           |
| `--text-sm`       | 13 / 18            | 400, 500 | 0                          | Table cells, controls, subtitles                          |
| `--text-md`       | 14 / 20            | 400, 500 | `--track-md`               | Body text, navigation, module titles (500)                |
| `--text-lg`       | 16 / 24            | 600      | `--track-lg`               | The gate panel title                                      |
| `--text-h1`       | 24 / 28            | 600      | `--track-h1`               | Page titles, through `PageHeader`                         |
| `--text-kpi`      | 28 / 32            | 600      | `--track-kpi`              | Headline card values                                      |
| `--text-headline` | 30 / 32            | 600      | `--track-kpi`              | The value above a featured chart, such as the daily chart |

Every table column header takes the `col-head` class from `src/app.css`: one step larger than the cells (`--text-md` against `--text-sm`) and weight 600. Change header type there, never in a table component.

In a headline value, set units such as `h`, `m`, `s`, and `%` smaller and muted. Render the value with `UnitValue`, which splits it with `valueParts` in `src/lib/format.ts`.

## Surfaces and space

The neutrals are zero-saturation grays. Use `--bg` for the page, `--surface` for cards, `--surface-sunken` for tracks and segmented controls, and `--surface-hover` for row and item hover. Text uses `--text`, `--text-muted`, and `--text-faint`. Each one reaches 4.5:1 contrast on all four surfaces in both themes.

Borders are alpha over whatever is below them. Use `--border` for dividers and table headers, `--border-strong` for emphasis, and `--border-row` for the line between table rows.

Cards are raised with the `--ring` shadow, not a border. A card that is a link or a button changes to `--ring-hover` on hover. Popovers and tooltips use `--shadow-popover`, and the gate panel uses `--shadow-panel`.

| Token              | Value | Use                                         |
| ------------------ | ----- | ------------------------------------------- |
| `--radius-control` | 6px   | Buttons, selects, dropdowns, navigation     |
| `--radius-card`    | 10px  | Cards and modules                           |
| `--radius-chip`    | 4px   | Badges, filter chips, delta chips           |
| `--radius-popover` | 8px   | Popovers, tooltips, notices                 |
| `--row-height`     | 34px  | Table rows and navigation items             |
| `--control-height` | 32px  | Buttons, selects, and the top bar controls  |
| `--content-max`    | 1480px | The widest the main column grows           |

Space comes from `--space-1` (4px) through `--space-6` (32px). The Overview lays out modules on a 12-column grid with a 16px gap. Modules in one row stretch to the same height.

## Motion

Motion explains a change. It never decorates, and nothing animates when a page first paints its data. Animate only `transform` and `opacity`, never `transition: all`.

| Token        | Value                         | Use                                                           |
| ------------ | ----------------------------- | ------------------------------------------------------------- |
| `--dur-fast` | 120ms                         | Hover, focus, tab switches, tooltips in and out               |
| `--dur-med`  | 200ms                         | A value that changes after a filter change, a chip that enters |
| `--dur-slow` | 240ms                         | Bar and bar-list size changes, the gate panel sliding in      |
| `--ease`     | `cubic-bezier(.2,0,.38,.9)`   | Most transitions                                              |
| `--ease-in`  | `cubic-bezier(0,0,.38,.9)`    | Elements that enter                                           |

The keyframe `fade-in` lives in `src/app.css`. The live dot in the top bar is the only looping animation. Loading skeletons (`Skeleton`) are still blocks that stay invisible for 200ms, so a fast load never flashes them. When a tab, filter, or range changes what a module shows, the view eases to the new data: chart bars take `barMotion()` from `src/lib/motion.ts`, ranked rows slide to their new rank with `animate:flip` at `viewChangeMs()`, and bars, meters, and heatmap cells transition their size or color at `--dur-slow`. A global rule turns every CSS animation and transition off under `prefers-reduced-motion`. A Svelte transition, such as the value swap in `StatStrip`, must read `prefers-reduced-motion` itself and set its duration to 0.

## Palette

The app uses six palette colors, defined once as `--palette-100` to `--palette-600`. Each color has one role. Use the color for its role and for nothing else.

| Slot  | Color     | Role                                                                                            | Tokens                                 |
| ----- | --------- | ----------------------------------------------------------------------------------------------- | -------------------------------------- |
| `100` | `#3A93E6` | Brand: active navigation, accent buttons, links, focus ring, "skip" badge, run counts           | `--accent`, `--focus`, `--chart-runs`  |
| `200` | `#BB82E3` | Flaky gates                                                                                     | `--flaky`                              |
| `300` | `#DA637A` | Failures: "fail" badge, failure counts, error notices, the failures chart series                | `--danger`, `--chart-failures`         |
| `400` | `#D98B08` | Warnings: stale data, degraded data                                                             | `--warn`                               |
| `500` | `#70A030` | Success: "pass" badge, the live indicator, time saved                                           | `--ok`, `--chart-saved`                |
| `600` | `#00BBB3` | Passes that gate-cache did not cache                                                            | `--info`                               |

Each role token except `--focus` and the chart tokens has a `-soft` partner, such as `--danger-soft`, for the background behind its text. `--neutral-soft` is the background of a neutral chip. Gray chart marks, such as bars for counts that are neither good nor bad, use `--chart-neutral`. Charts that split runs by outcome color each outcome with `--chart-skip`, `--chart-pass`, `--chart-pass-unrecorded`, `--chart-fail`, and `--chart-uncached`, which follow the outcome badge roles and use gray for uncached runs.

### Gate series

A chart that splits a total by gate, such as Time spent, colors the gates with `--chart-series-1` to `--chart-series-5` in rank order, and uses `--chart-neutral` gray for Other. Get a color with `seriesColor` in `src/lib/spent.ts`. The five colors are blue, magenta, teal, violet, and cyan. They avoid green, red, and amber, because those colors mean saved, failures, and warnings.

Neighbors in rank order pass the dataviz palette checks in both themes, and teal next to magenta is the closest pair for readers with deuteranopia. Pairs that are not neighbors are close: teal and cyan (3 and 5) for every reader, and blue and violet (1 and 4) and magenta and cyan (2 and 5) for readers with deuteranopia. A stacked chart puts only neighbors side by side. A gate chart always names each part in a legend and in its tooltip, so color never identifies a gate alone. Stacked segments touch with no gap or stroke between them.

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
2. Use the role token (`--accent`, `--danger`, and so on) for text, icons, and borders. The palette slots are mid-tones, and they are too light for small text on white. The role tokens are darker shades in light mode and lighter shades in dark mode, and each one reaches 4.5:1 contrast on `--bg`, `--surface`, `--surface-sunken`, `--surface-hover`, and its `-soft` background.
3. Use a palette slot directly only for chart marks, dots, and the focus ring. Time saved is green, runs are blue, and failures are red in every chart, bar, sparkline, and heatmap.
4. Never show blue (`100`) and violet (`200`) as two series in one chart. Readers with protanopia cannot tell them apart. The gate series are the one exception: they put blue and violet at ranks 1 and 4, never side by side, and name every part in a legend and a tooltip.
5. Never let color carry meaning alone. A badge has a text label, a chart has a legend and a screen-reader table, a delta chip has an arrow icon and screen-reader text, and a count has a label. A picked chart mark gets an outline or ring, the other marks dim, and `aria-pressed` or `aria-selected` states the pick.
6. Values, labels, and legends use the text tokens, never a series color. A colored swatch or bar beside them carries the identity.
7. If you add a token, follow the derivation rule in the comment at the top of `src/app.css`, then measure the contrast of each new text token in both themes and record it in that comment.

## Components

Use an existing component before you write markup of your own. If a page needs a control that no component covers, add a shared component in `src/lib/components/` and use it from the page. Do not style a one-off control inside a page.

| Need                                                  | Component                         |
| ----------------------------------------------------- | --------------------------------- |
| A page title, subtitle, and page filter chips         | `PageHeader`                      |
| A Lucide icon                                         | `Icon` (add the name to its `ICONS` map first) |
| An explanation of a label on hover, focus, or click: an info icon on cards, or the label itself with a dotted underline (`explained` class) on table headers through a column's `info` | `InfoTip`  |
| A table of rows, sortable, with optional row clicks   | `DataTable`                       |
| The table of gates on the Gates page                  | `GateTable`                       |
| Headline numbers as cards with deltas and sparklines  | `StatStrip`, with stats from `summaryStats` |
| A small trend line inside a card                      | `Sparkline`                       |
| Time saved and failures per day                       | `DailyChart`                      |
| Time spent per day, stacked by gate                   | `SpentChart`                      |
| Run time of one gate over time                        | `TrendChart`                      |
| Any tooltip: a chart's values or a plain explanation  | `TooltipSurface`, the one tooltip surface; a chart renders it inside a LayerChart `Tooltip.Root` with `variant="none"` |
| The outcome of one run                                | `OutcomeBadge`                    |
| A run's time in a table cell                          | `TimeValue`, with `ranText` or `savedText` from `src/lib/events.ts` |
| Any other short label, such as "flaky"                | `Badge` (pick the tone by role)   |
| A change, such as "+6%" or "slower by 20%"           | `TrendBadge`                      |
| A value with smaller units, such as "6h 38m"         | `UnitValue`                       |
| A thin inline bar for a row's share                   | `Meter`                           |
| A page-local filter that the user can remove          | `FilterChip`                      |
| A labeled choice from a short list, such as a filter  | `Select` (a native `<select>`)    |
| A command                                             | `Button` (`accent` for at most one control per view) |
| A one-line message above page content                 | `Notice` (`info`, `warning`, `error`) |
| A region with no data                                 | `EmptyState`, with copy from `src/lib/scope.ts` |
| A placeholder block while data loads                  | `Skeleton`                        |
| A button that opens a popover of choices              | `Dropdown`                        |
| A homepage card with title, loading, error, empty, a "see all" link, and footer | `Module` (`more` for the link) |
| Tabs that pick what a module measures                 | `MetricTabs`                      |
| One cell per day over the date range                  | `CalendarHeatmap`                 |
| Activity by weekday and hour, with totals             | `HourHeatmap`                     |
| A numbered top-N list with inline bars, such as Top gates | `RankedList`                  |
| The share of each outcome as one stacked bar          | `OutcomeMix`                      |
| The share of each part of another whole, such as how waits ended | `ShareMix`             |
| A bar per named row with numeric columns, such as Breakdown | `BarList`, with rows from `breakdownBars` |
| The repo filter, the date range, and freshness        | `TopBar` (already in the app shell), with `RepoPicker` and `RangePicker` |

## Pages

Every page follows the same pattern:

- Open with `PageHeader`. Its subtitle names the repo filter and the date range, from `scopeSubtitle` in `src/lib/scope.ts`.
- Load data with `createQuery` from `src/lib/query.svelte.ts`. The page then refetches when new runs arrive and when a filter changes.
- Show loading with `Skeleton` blocks (`Module` does this for you), an error `Notice`, and an `EmptyState` the same way the existing pages do.
- Name the active filter in empty states, for example "No runs in the last 7 days for api-server."
- Use the hash router in `src/lib/router.svelte.ts` for links, so that the browser back button works.
- Give a module's "All gates" style link to `Module` as `more`, and its footnotes as the `footer` snippet.
