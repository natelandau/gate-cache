# gate-cache

gate-cache is a CLI that wraps a lint or test command. It skips the command when the same named command already passed on the same git tree. The code is in `src/gate_cache/` and the tests are in `tests/`. `README.md` and the documentation site in `docs/` hold the user documentation. `CONTRIBUTING.md` holds the developer setup and workflow for people. `src/gate_cache/agent/skill.md` and `prompt.md` hold the guides for coding agents that `gate-cache --skill` and `--prompt` print. [Agent guides](#agent-guides) sets what goes in them.

## Purpose

gate-cache has three goals:

1. **Save time.** Spend no time on lint and test runs that cannot give a new result. Today, gate-cache skips a command that already passed on the same content.
2. **Help developers manage their test and lint suites.** Give developers what they need to fix flaky gates, cut what their suites cost, and find where to improve. Today, the run stats and the dashboard serve this goal.
3. **Keep up as agents multiply tests.** Coding agents add tests fast and run the same gates again and again, often from several worktrees at the same time. Today, the `gate-cache:` stderr lines, the exit codes, the wait and lock behavior, and the `--skill` guide serve this goal.

No goal justifies a wrong skip. A skip of a command that would fail is the worst bug gate-cache can have, because it breaks the trust that the other goals depend on. When in doubt, run the command.

## Public documentation

`docs/` is the source of the documentation site at https://natelandau.github.io/gate-cache/. Zensical builds it from `zensical.toml`, and each release publishes it. The README is a short introduction that links to the site.

- The reader is a developer who adds gate-cache to a project. Give that reader enough to install, use, configure, and troubleshoot gate-cache, and no more. Leave out how the code works inside, such as algorithms, internal file layouts, and edge cases that the reader will not meet. Include a limit, threshold, or condition when it changes what the reader sees or must do, such as how long data is kept or how many runs a dashboard note counts. Leave it out when it only explains the code.
- Use words that any developer knows. Never use colloquialisms, terms coined in a spec or a session, or names from the code, such as module, function, or internal concept names. When the reader must know a term that gate-cache prints, such as "gate" or "tree", explain it where it first appears.
- Never assume which tools the reader has or knows. Assume only git, gate-cache, a shell, and major languages and operating systems, such as Python, Node, Ruby, macOS, and Linux. Any other tool, such as a task runner, a package manager like uv, or a hook manager like prek, is optional: show it as one of several choices, explain what it is, or leave it out. Never take the tools or setup of this repository or this computer as what readers use. This rule also applies to `src/gate_cache/agent/skill.md` and `prompt.md`, because agents follow them in repositories with other tools.
- The site is not a record of changes. `CHANGELOG.md` is. Change a page only when a change alters something that the page tells the reader to do or expect. Then rewrite the affected text so the page reads as one whole. Do not add a sentence for each fix, tweak, new check, or supported edge case. A detail goes on a page because the reader needs it to use gate-cache or to trust what it shows, not because the code has it, a spec names it, or a review flags that the page omits it.
- `docs/reference/agent-guide.md` is generated from `src/gate_cache/agent/skill.md` and is not committed. Edit the source, not the page. The site links to `CHANGELOG.md` and `CONTRIBUTING.md` in the repository and does not copy them.
- `docs/reference/marker-format.md` documents a public contract for tools that read markers. A core test runs its shell snippets.

## Agent guides

`gate-cache --skill` prints `src/gate_cache/agent/skill.md`. `gate-cache --prompt` prints `prompt.md`.

- The skill is for an agent that sets up, configures, or troubleshoots gate-cache in a project, or that must learn the CLI. It holds the rules, pitfalls, and workflows for that work. An agent in a normal development session does not read it.
- An agent in a normal session sees only the `gate-cache:` stderr lines of the gate run, the `error:` and `hint:` lines of the other commands, and the exit codes. Each line must make sense with no guide.
- Change the skill only when a change alters what an agent does to set up, configure, or troubleshoot gate-cache, or how it uses the CLI. The skill is not a list of every message, option, or behavior. A new message or behavior does not go in the skill only because the skill omits it.
- `prompt.md` holds only a few steps and the questions for the user. The agent learns the rest from the skill.

## Conventions

- A command that deletes data on request, such as `clear` and `stats clear`, calls `commands.prompt.confirm_deletion` and offers `-y`/`--yes`. Automatic cleanup, such as marker pruning, archive retention, and temp files, deletes with no prompt.
- `gate-cache --help` stays short and written for people. One line tells agents to run `--skill`.

## Worktrees

Do all work in a git worktree under `.worktrees/`, never in the main checkout. Several sessions can work on this repository at the same time, and they all share the main checkout. Create the worktree with `git worktree add .worktrees/<name> -b <branch>`, then run `uv sync` in it before you run any duty.

## Commands

Run linters and tests only through these duties, never directly, so every run shares the same gate-cache markers.

- `uv run duty lint` runs ruff, the ruff format check, ty, typos, the prek hooks, and the strict docs build. To run one gate, use `uv run duty ruff`, `format`, `ty`, `typos`, `prek`, or `docs_check`.
- `uv run duty test` runs the four test suites. Each suite skips when nothing in its paths changed since it last passed. If the change touches `frontend/`, the frontend suite runs and needs Node.
- To run one suite, use `uv run duty test_core` (the gate and the CLI), `test_server` (the Python dashboard server), `test_tooling` (CI, duties, and scripts), or `frontend_test` (the dashboard UI). Core and server each have their own 90% coverage threshold, set in `tests/core/coverage.toml` and `tests/server/coverage.toml`.
- `uv run duty test -k NAME --no-cov` runs a subset of the Python tests, with no gate. Without `--no-cov`, the subset fails the 90% coverage threshold.
- Each test file goes in `tests/core/`, `tests/server/`, or `tests/tooling/`. A test module never imports from another suite's test module. Shared helpers go in `tests/conftest.py`.
- `SUITES` in `duties.py` holds the paths of each suite. The `paths:` filters in `.github/workflows/tests-*.yml` must match it, and `tests/tooling/test_workflows.py` fails when they do not. When you change a suite's paths, change both. A release runs every suite.
- `uv run duty frontend_check`, `frontend_test`, and `frontend_build` check, test, and build the dashboard UI in `frontend/`. These three duties, and `duty test` when `frontend/` changed, need Node. Each one runs `npm ci` first when `frontend/node_modules` is missing or older than `frontend/package-lock.json`.
- To work on the dashboard UI with live reload, run `uv run gate-cache dashboard --no-browser --port 7879`, then `npm --prefix frontend run dev`. The Vite dev server sends `/api` requests to port 7879.
- When you run gate-cache or the dashboard by hand on test data, set `GATE_CACHE_DATA_DIR` to a temporary directory and `GATE_CACHE_STATS=1`, so the run never writes to your real stats.
- Before you change the dashboard UI, read `frontend/DESIGN.md` for the palette roles, the color rules, and which shared component to use.
- `uv run duty docs` serves the documentation site with live reload at http://localhost:8010/gate-cache/. `uv run duty docs_check` builds it in strict mode, so a broken link fails.
- `uv run duty dist_check dist/*` checks that built wheels and sdists ship the dashboard UI and the agent guides. Run it after `frontend_build` and `uv build`.

## Checking the dashboard UI

To see a dashboard change in a browser without a person, take headless screenshots:

1. Set `GATE_CACHE_DATA_DIR` to a temporary directory, and seed it with a synthetic `events.jsonl` or with runs recorded under `GATE_CACHE_STATS=1`.
2. Start the dashboard: `uv run gate-cache dashboard --no-browser --port 7879`.
3. Take a screenshot with Chrome: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --virtual-time-budget=8000 --window-size=1400,2200 --screenshot=out.png http://localhost:7879/`. Add `--force-dark-mode` for the dark theme.

A gate panel opens at `#/gates/<repo>/<name>`, with each part URI-encoded. To pick the range and repos, put a JSON value such as `{"repos":[],"range":"1y"}` in the `gate-cache.filters` localStorage key before the page loads.

The Chrome command line clips widths less than about 500px, and it cannot hover or click. For a phone width, a hover, an open menu, or a clipped screenshot, use Playwright. Install it in a scratch directory and set `executablePath` to the installed Chrome or to a cached headless shell, such as `~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell`. No browser download is necessary. Playwright also sets `colorScheme: "dark"` and seeds localStorage in an init script.

Only one dashboard runs for each data directory. A second `gate-cache dashboard` prints `dashboard already running` and exits 0, even on another port. To use real data while the user's dashboard runs, copy the data directory (`gate-cache stats` prints it) to a temporary directory. Delete `dashboard.lock` and `dashboard.url` from the copy, and point `GATE_CACHE_DATA_DIR` at it.

## Commits

Before you open a pull request, fast-forward a branch onto `main`, or squash a branch into `main`, compare `src/gate_cache/agent/skill.md` (the `gate-cache --skill` guide) with the branch diff. If the branch makes the guide wrong, or changes how an agent sets up, configures, or troubleshoots gate-cache, update the guide on the branch. [Agent guides](#agent-guides) sets the scope.

Mark a commit as a breaking change (`!` in the subject and a `BREAKING CHANGE:` footer) only when it breaks the CLI: a removed or renamed command or flag, a changed exit code, or a change to the CLI's output. A change to the dashboard UI is never breaking, even when it removes a page.

## Gates

The duties run each gate through the gate-cache of this working copy. If a change breaks gate-cache, the duties fail too. A gate that already passed on the same content, committed or not, prints `already passed on tree` and skips. To force a full run, set `GATE_CACHE_DISABLE=1`.

Before you add or change a gate, or change the paths in `SUITES` or `DOCS_PATHS`, run `uv run gate-cache --skill` and follow its rules for names, paths, and checks.
