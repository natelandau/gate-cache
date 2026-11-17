# Dashboard design guide

Read this page before you add or change anything in the dashboard UI. It gives the rules that the code cannot show: which color means what, which component to use, and how a page must behave. The token values live in `src/app.css`. The components live in `src/lib/components/`, and each one documents its props in an `@component` block.

## Principles

The dashboard is an operations tool that people open many times a day. These principles decide most design questions:

- Data comes first. Use dense rows (28px), tabular numbers, and small type. Do not add large cards, hero sections, or decorative motion.
- Freshness and filters are always visible. Every page reads the global date range, and the top bar shows when the data last updated. Every page except the repo detail page reads the global repo filter. The repo detail page shows its own repo, so its empty-state hints must not suggest a change to the repo filter.
- Familiar controls win over new ones. Use native `<select>`, radio buttons, and buttons, styled with tokens.
- Every control is reachable with the keyboard and shows a visible focus ring. Motion respects `prefers-reduced-motion`.
- Light and dark themes are equal. Check every change in both. The theme button in the top bar switches between System (the default), Light, and Dark.

## Palette

The app uses six palette colors, defined once as `--palette-100` to `--palette-600`. Each color has one role. Use the color for its role and for nothing else.

| Slot  | Color     | Role                                                                                          | Tokens                         |
| ----- | --------- | --------------------------------------------------------------------------------------------- | ------------------------------ |
| `100` | `#3A93E6` | Brand: favicon, active navigation, accent buttons, links, focus ring, "skip" badge, time saved | `--accent`, `--focus`, `--chart-saved` |
| `200` | `#BB82E3` | Flaky gates                                                                                   | `--flaky`                      |
| `300` | `#DA637A` | Failures: "fail" badge, failure counts, error notices, the failures chart series              | `--danger`, `--chart-failures` |
| `400` | `#D98B08` | Warnings: stale data, degraded data                                                           | `--warn`                       |
| `500` | `#70A030` | Success: "pass" badge, the live indicator                                                     | `--ok`                         |
| `600` | `#00BBB3` | Passes that gate-cache did not cache                                                          | `--info`                       |

Each role token except `--focus` and the chart tokens has a `-soft` partner, such as `--danger-soft`, for the background behind its text. Gray text, surfaces, and borders use the neutral tokens (`--text`, `--text-muted`, `--surface`, `--border`, and the others in `src/app.css`).

### Color rules

These rules keep the palette readable and consistent:

1. Never write a hex value or `rgb()` in a component. Use a token from `src/app.css`. If no token fits, add one there with a light value and a dark value. Light values live under `:root`, and dark values live under `:root[data-theme="dark"]`.
2. Use the role token (`--accent`, `--danger`, and so on) for text, icons, and borders. The palette slots are mid-tones, and they are too light for small text on white. The role tokens are darker shades in light mode and lighter shades in dark mode, and each one reaches 4.5:1 contrast on `--bg`, `--surface`, and its `-soft` background.
3. Use a palette slot directly only for chart marks, dots, the favicon, and the focus ring.
4. Never show blue (`100`) and violet (`200`) as two series in one chart. Readers with protanopia cannot tell them apart.
5. Never let color carry meaning alone. A badge has a text label, a chart has a legend and a screen-reader table, and a count has a label.
6. If you add a token, follow the derivation rule in the comment at the top of `src/app.css`, then measure the contrast of each new text token in both themes.

## Components

Use an existing component before you write markup of your own. If a page needs a control that no component covers, add a shared component in `src/lib/components/` and use it from the page. Do not style a one-off control inside a page.

| Need                                                  | Component                         |
| ----------------------------------------------------- | --------------------------------- |
| A table of rows, sortable, with optional row clicks   | `DataTable`                       |
| The table of gates (Gates page and repo page)         | `GateTable`                       |
| A row of headline numbers                             | `StatStrip`                       |
| Time saved and failures per day                       | `DailyChart`                      |
| Run time of one gate over time                        | `TrendChart`                      |
| The outcome of one run                                | `OutcomeBadge`                    |
| Any other short label, such as "flaky"                | `Badge` (pick the tone by role)   |
| A command                                             | `Button` (`accent` for at most one control per view) |
| A one-line message above page content                 | `Notice` (`info`, `warning`, `error`) |
| A region with no data                                 | `EmptyState`, with copy from `src/lib/scope.ts` |
| The repo filter, the date range, and freshness        | `TopBar` (already in the app shell) |

## Pages

Every page follows the same pattern:

- Load data with `createQuery` from `src/lib/query.svelte.ts`. The page then refetches when new runs arrive and when a filter changes.
- Show the loading text, an error `Notice`, and an `EmptyState` the same way the existing pages do.
- Name the active filter in empty states, for example "No runs in the last 7 days for api-server."
- Use the hash router in `src/lib/router.svelte.ts` for links, so that the browser back button works.
