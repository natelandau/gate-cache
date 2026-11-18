# gate-cache

gate-cache is a CLI that wraps a lint or test command. It skips the command when the same named command already passed on the same git tree. The code is in `src/gate_cache/` and the tests are in `tests/`. `README.md` and the documentation site in `docs/` hold the user documentation. `CONTRIBUTING.md` holds the developer setup and workflow for people. `src/gate_cache/agent/skill.md` and `prompt.md` hold the guides for coding agents that `gate-cache --skill` and `--prompt` print. When a change alters behavior, an option, or a message that a guide describes, update the guide in the same change.

## Purpose

gate-cache has three goals:

1. **Save time.** Spend no time on lint and test runs that cannot give a new result. Today, gate-cache skips a command that already passed on the same content.
2. **Help developers manage their test and lint suites.** Give developers what they need to fix flaky gates, cut what their suites cost, and find where to improve. Today, the run stats and the dashboard serve this goal.
3. **Keep up as agents multiply tests.** Coding agents add tests fast and run the same gates again and again, often from several worktrees at the same time. Today, the `gate-cache:` stderr lines, the exit codes, the wait and lock behavior, and the `--skill` guide serve this goal.

No goal justifies a wrong skip. A skip of a command that would fail is the worst bug gate-cache can have, because it breaks the trust that the other goals depend on. When in doubt, run the command.

## Public documentation

`docs/` is the source of the documentation site at https://natelandau.github.io/gate-cache/. Zensical builds it from `zensical.toml`, and each release publishes it. The README is a short introduction that links to the site.

- The reader is a developer who adds gate-cache to a project. Give that reader enough to install, use, configure, and troubleshoot gate-cache, and no more. Leave out how the code works inside, the algorithms, and edge cases that the reader will not meet.
- Use words that any developer knows. Never use colloquialisms, terms coined in a spec or a session, or names from the code, such as module, function, or internal concept names. When the reader must know a term that gate-cache prints, such as "gate" or "tree", explain it where it first appears.
- Never assume which tools the reader has or knows. Assume only git, gate-cache, a shell, and major languages and operating systems, such as Python, Node, Ruby, macOS, and Linux. Any other tool, such as a task runner, a package manager like uv, or a hook manager like prek, is optional: show it as one of several choices, explain what it is, or leave it out. Never take the tools or setup of this repository or this computer as what readers use. This rule also applies to `src/gate_cache/agent/skill.md` and `prompt.md`, because agents follow them in repositories with other tools.
- The site is not a record of changes. `CHANGELOG.md` is. Change a page only when a change alters something that the page tells the reader to do or expect. Then rewrite the affected text so the page reads as one whole. Do not add a sentence for each fix, tweak, new check, or supported edge case.
- `docs/reference/agent-guide.md` is generated from `src/gate_cache/agent/skill.md` and is not committed. Edit the source, not the page. The site links to `CHANGELOG.md` and `CONTRIBUTING.md` in the repository and does not copy them.
- `docs/reference/marker-format.md` documents a public contract for tools that read markers. A core test runs its shell snippets.

## Conventions

- A command that deletes data on request, such as `clear` and `stats clear`, calls `console.confirm_deletion` and offers `-y`/`--yes`. Automatic cleanup, such as marker pruning, archive retention, and temp files, deletes with no prompt.
- `gate-cache --help` stays short and written for people. One line tells agents to run `--skill`. Agent guidance, such as rules, pitfalls, and workflows, goes in `src/gate_cache/agent/skill.md`. `prompt.md` holds only a few steps and the questions for the user. The agent learns the rest from the skill.

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

## Commits

Before you open a pull request, fast-forward a branch onto `main`, or squash a branch into `main`, compare `src/gate_cache/agent/skill.md` (the `gate-cache --skill` guide) with the branch diff. If the branch adds or changes a feature, option, or message that the guide describes or omits, update the guide on the branch.

Mark a commit as a breaking change (`!` in the subject and a `BREAKING CHANGE:` footer) only when it breaks the CLI: a removed or renamed command or flag, a changed exit code, or a change to the CLI's output. A change to the dashboard UI is never breaking, even when it removes a page.

## Gates

The duties run each gate through the gate-cache of this working copy. If a change breaks gate-cache, the duties fail too. A gate that already passed on the same content, committed or not, prints `already passed on tree` and skips. To force a full run, set `GATE_CACHE_DISABLE=1`.
