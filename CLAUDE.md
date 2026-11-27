# gate-cache

CLI that wraps a lint or test command and skips it when the same named command already passed on the same git tree.

- Code: `src/gate_cache/`. Tests: `tests/`.
- User docs: `README.md` and the site in `docs/`. Developer setup for people: `CONTRIBUTING.md`.
- Agent guides: `src/gate_cache/agent/skill.md` and `prompt.md`, printed by `gate-cache --skill` and `--prompt`. See [Agent guides](#agent-guides).

## Purpose

1. **Save time.** No lint or test run that cannot give a new result. Served by skipping commands that already passed on the same content.
2. **Help developers manage their suites.** Fix flaky gates, cut suite cost, find where to improve. Served by run stats and the dashboard.
3. **Keep up as agents multiply tests.** Agents add tests fast and rerun gates, often from several worktrees at once. Served by the `gate-cache:` stderr lines, exit codes, wait and lock behavior, and the `--skill` guide.

No goal justifies a wrong skip. Skipping a command that would fail is the worst possible bug: it breaks the trust the other goals depend on. In doubt, run the command.

## Public documentation

`docs/` is the source of https://natelandau.github.io/gate-cache/, built by Zensical from `zensical.toml` and published on each release. The README is a short introduction linking to the site.

- Reader: a developer adding gate-cache to a project. Give enough to install, use, configure, and troubleshoot, no more. Leave out internals: algorithms, internal file layouts, edge cases the reader will not meet. Include a limit, threshold, or condition only when it changes what the reader sees or must do (how long data is kept, how many runs a dashboard note counts).
- Words any developer knows. No colloquialisms, terms coined in a spec or session, or code names (modules, functions, internal concepts). Explain a printed term such as "gate" or "tree" where it first appears.
- Assume only git, gate-cache, a shell, and major languages and operating systems (Python, Node, Ruby, macOS, Linux). Show any other tool (task runner, uv, prek) as one of several choices, explain it, or omit it. Never present this repository's or this computer's tools as the reader's. Also applies to `skill.md` and `prompt.md`, which agents follow in repositories with other tools.
- `CHANGELOG.md` is the record of changes, not the site. Change a page only when a change alters what it tells the reader to do or expect, then rewrite the affected text so the page reads as one whole. No sentence per fix, tweak, check, or edge case. A detail earns its place because the reader needs it to use gate-cache or trust what it shows, not because the code has it, a spec names it, or a review notes its absence.
- `docs/reference/agent-guide.md` is generated from `skill.md` and not committed. Edit the source. The site links to `CHANGELOG.md` and `CONTRIBUTING.md` in the repository instead of copying them.
- `docs/reference/marker-format.md` is a public contract for tools that read markers. A core test runs its shell snippets.

## Agent guides

- Write `skill.md` and `prompt.md` for an agent reader, not in the docs style: imperative fragments, tables for mappings, no filler. The Agent guide page renders `skill.md` as is.
- Skill reader: an agent that sets up, configures, or troubleshoots gate-cache, or must learn the CLI. It holds the rules, pitfalls, and workflows for that work. An agent in a normal session never reads it.
- A normal-session agent sees only the gate run's `gate-cache:` stderr lines, other commands' `error:` and `hint:` lines, and exit codes. Each line must make sense with no guide.
- Change the skill only when a change alters how an agent sets up, configures, or troubleshoots gate-cache, or uses the CLI. It is not a catalog of messages, options, or behaviors; omission alone is no reason to add one.
- `prompt.md`: a few steps and the questions for the user. The agent learns the rest from the skill.
- Core tests check that every message the skill quotes still comes from the code, and that every guide section `prompt.md` names is a skill heading.

## Conventions

- A command that deletes data on request (`clear`, `stats clear`) calls `commands.prompt.confirm_deletion` and offers `-y`/`--yes`. Automatic cleanup (marker pruning, archive retention, temp files) deletes with no prompt.
- `gate-cache --help` stays short and written for people, with one line telling agents to run `--skill`.

## Worktrees

Work only in a git worktree under `.worktrees/`, never the main checkout; several sessions share the main checkout at once. `git worktree add .worktrees/<name> -b <branch>`, then `uv sync` in it before any duty.

## Commands

Run linters and tests only through these duties, never directly, so every run shares the same gate-cache markers.

- `uv run duty lint`: ruff, ruff format check, ty, typos, prek hooks, strict docs build. One gate: `uv run duty ruff`, `format`, `ty`, `typos`, `prek`, or `docs_check`.
- `uv run duty test`: all four suites. Each skips when nothing in its paths changed since its last pass. Changes under `frontend/` run the frontend suite, which needs Node.
- One suite: `uv run duty test_core` (gate and CLI), `test_server` (Python dashboard server), `test_tooling` (CI, duties, scripts), `frontend_test` (dashboard UI). Core and server each enforce 90% coverage, set in `tests/core/coverage.toml` and `tests/server/coverage.toml`.
- Subset: `uv run duty test -k NAME --no-cov` runs ungated. Without `--no-cov` the subset fails the coverage threshold.
- Test files go in `tests/core/`, `tests/server/`, or `tests/tooling/`. Never import from another suite's test module; shared helpers go in `tests/conftest.py`.
- `SUITES` in `duties.py` holds each suite's paths. The `paths:` filters in `.github/workflows/tests-*.yml` must match; `tests/tooling/test_workflows.py` fails otherwise. Change both together. A release runs every suite.
- `uv run duty frontend_check`, `frontend_test`, `frontend_build`: check, test, build the dashboard UI in `frontend/`. These, and `duty test` when `frontend/` changed, need Node and run `npm ci` first when `frontend/node_modules` is missing or older than `frontend/package-lock.json`.
- Dashboard UI live reload: `uv run gate-cache dashboard --no-browser --port 7879`, then `npm --prefix frontend run dev`. Vite proxies `/api` to port 7879.
- Running gate-cache or the dashboard by hand on test data: set `GATE_CACHE_DATA_DIR` to a temporary directory and `GATE_CACHE_STATS=1`, so real stats stay untouched.
- Before changing the dashboard UI, read `frontend/DESIGN.md`: palette roles, color rules, which shared component to use.
- `uv run duty docs`: live-reload site at http://localhost:8010/gate-cache/. `uv run duty docs_check`: strict build, broken links fail.
- `uv run duty dist_check dist/*`: checks built wheels and sdists ship the dashboard UI and agent guides. Run after `frontend_build` and `uv build`.

## Checking the dashboard UI

Headless screenshots, to see a dashboard change without a person:

1. Set `GATE_CACHE_DATA_DIR` to a temporary directory. Seed it with a synthetic `events.jsonl` or runs recorded under `GATE_CACHE_STATS=1`.
2. `uv run gate-cache dashboard --no-browser --port 7879`.
3. `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --virtual-time-budget=8000 --window-size=1400,2200 --screenshot=out.png http://localhost:7879/`. Add `--force-dark-mode` for the dark theme.

- Gate panel: `#/gates/<repo>/<name>`, each part URI-encoded.
- Range and repos: put JSON such as `{"repos":[],"range":"1y"}` in the `gate-cache.filters` localStorage key before page load.
- Chrome's command line clips widths under about 500px and cannot hover or click. For phone width, hover, open menus, or clipped shots, use Playwright: install it in a scratch directory and set `executablePath` to installed Chrome or a cached headless shell such as `~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell` (no browser download). Set `colorScheme: "dark"` and seed localStorage in an init script.
- One dashboard per data directory. A second `gate-cache dashboard` prints `dashboard already running` and exits 0, even on another port. To use real data while the user's dashboard runs: copy the data directory (`gate-cache stats` prints it) to a temporary directory, delete `dashboard.lock` and `dashboard.url` from the copy, point `GATE_CACHE_DATA_DIR` at it.

## Commits

- Before opening a pull request, or fast-forwarding or squashing a branch onto `main`: compare `skill.md` with the branch diff. Branch makes the guide wrong, or changes how an agent sets up, configures, or troubleshoots gate-cache: update the guide on the branch, scoped by [Agent guides](#agent-guides).
- Change to `skill.md` or `prompt.md`: type `feat` or `fix`, never `docs`. The guides ship in the package, and commitizen leaves `docs` commits out of the changelog and the version bump.
- Breaking change (`!` in the subject plus a `BREAKING CHANGE:` footer) only when the CLI breaks: a removed or renamed command or flag, a changed exit code, or changed CLI output. A dashboard UI change is never breaking, even when it removes a page.

## Gates

The duties run each gate through this working copy's gate-cache, so a change that breaks gate-cache fails the duties too. A gate that already passed on the same content, committed or not, prints `already passed on tree` and skips. Full run: `GATE_CACHE_DISABLE=1`.

Before adding or changing a gate, or changing the paths in `SUITES` or `DOCS_PATHS`, run `uv run gate-cache --skill` and follow its rules for names, paths, and checks.
