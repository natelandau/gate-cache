# gate-cache

gate-cache is a CLI that wraps a lint or test command. It skips the command when the same named command already passed on the same git tree. The code is in `src/gate_cache/` and the tests are in `tests/`. `README.md` and `docs/how-it-works.md` hold the user documentation. `src/gate_cache/agent/skill.md` and `prompt.md` hold the guides for coding agents that `gate-cache --skill` and `--prompt` print. When a change alters behavior, an option, or a message that a guide describes, update the guide in the same change.

## Conventions

- A command that deletes data on request, such as `clear` and `stats clear`, calls `console.confirm_deletion` and offers `-y`/`--yes`. Automatic cleanup, such as marker pruning, archive retention, and temp files, deletes with no prompt.
- `gate-cache --help` stays short and written for people. One line tells agents to run `--skill`. Agent guidance, such as rules, pitfalls, and workflows, goes in `src/gate_cache/agent/skill.md`. `prompt.md` holds only a few steps and the questions for the user. The agent learns the rest from the skill.

## Worktrees

Do all work in a git worktree under `.worktrees/`, never in the main checkout. Several sessions can work on this repository at the same time, and they all share the main checkout. Create the worktree with `git worktree add .worktrees/<name> -b <branch>`, then run `uv sync` in it before you run any duty.

## Commands

Run linters and tests only through these duties, never directly, so every run shares the same gate-cache markers.

- `uv run duty lint` runs ruff, the ruff format check, ty, typos, and the prek hooks. To run one gate, use `uv run duty ruff`, `format`, `ty`, `typos`, or `prek`.
- `uv run duty test` runs the four test suites. Each suite skips when nothing in its paths changed since it last passed. If the change touches `frontend/`, the frontend suite runs and needs Node.
- To run one suite, use `uv run duty test_core` (the gate and the CLI), `test_server` (the Python dashboard server), `test_tooling` (CI, duties, and scripts), or `frontend_test` (the dashboard UI). Core and server each have their own 90% coverage threshold, set in `tests/core/coverage.toml` and `tests/server/coverage.toml`.
- `uv run duty test -k NAME --no-cov` runs a subset of the Python tests, with no gate. Without `--no-cov`, the subset fails the 90% coverage threshold.
- Each test file goes in `tests/core/`, `tests/server/`, or `tests/tooling/`. A test module never imports from another suite's test module. Shared helpers go in `tests/conftest.py`.
- `SUITES` in `duties.py` holds the paths of each suite. The `paths:` filters in `.github/workflows/tests-*.yml` must match it, and `tests/tooling/test_workflows.py` fails when they do not. When you change a suite's paths, change both. A release runs every suite.
- `uv run duty frontend_check`, `frontend_test`, and `frontend_build` check, test, and build the dashboard UI in `frontend/`. These three duties, and `duty test` when `frontend/` changed, need Node.
- To work on the dashboard UI with live reload, run `uv run gate-cache dashboard --no-browser --port 7879`, then `npm --prefix frontend run dev`. The Vite dev server sends `/api` requests to port 7879.
- Before you change the dashboard UI, read `frontend/DESIGN.md` for the palette roles, the color rules, and which shared component to use.
- `uv run duty dist_check dist/*` checks that built wheels and sdists ship the dashboard UI and the agent guides. Run it after `frontend_build` and `uv build`.

## Gates

The duties run each gate through the gate-cache of this working copy. If a change breaks gate-cache, the duties fail too. A gate that already passed on the same content, committed or not, prints `already passed on tree` and skips. To force a full run, set `GATE_CACHE_DISABLE=1`.
