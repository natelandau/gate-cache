# Contributing to gate-cache

This guide tells you how to set up gate-cache for development, run the checks, work on the dashboard, and send a change.

## Requirements

- [uv](https://docs.astral.sh/uv/). uv installs the Python version in `.python-version`.
- Node, the version in `.node-version`. You need Node only to work on the dashboard UI in `frontend/`.
- git.

## Set up

1. Clone the repository.
2. Install the dependencies:

    ```sh
    uv sync
    ```

3. Install the git hooks:

    ```sh
    uv run prek install
    ```

The hooks check each commit message and run the linters and tests before a commit and a push.

## Project layout

| Path                       | Holds                                                                                |
| -------------------------- | ------------------------------------------------------------------------------------ |
| `src/gate_cache/`          | The CLI, the gate, and the stats recorder.                                           |
| `src/gate_cache/dashboard/` | The Python server of the dashboard.                                                  |
| `src/gate_cache/agent/`    | `skill.md` and `prompt.md`, the guides that `gate-cache --skill` and `--prompt` print. |
| `frontend/`                | The dashboard UI.                                                                    |
| `tests/`                   | The Python tests, in the `core/`, `server/`, and `tooling/` suites.                  |
| `docs/`                    | The documentation site.                                                              |

## Run the checks

Run the linters and the tests only through these `duty` tasks. The tasks run each check through the gate-cache of your working copy, so a check that already passed on the same files skips.

| Command                   | Runs                                                                  |
| ------------------------- | --------------------------------------------------------------------- |
| `uv run duty lint`        | ruff, the ruff format check, ty, typos, the prek hooks, and the strict docs build. |
| `uv run duty test`        | The four test suites. Each suite skips when none of its files changed. |
| `uv run duty test_core`   | The tests of the gate and the CLI.                                    |
| `uv run duty test_server` | The tests of the dashboard server.                                    |
| `uv run duty test_tooling`| The tests of CI, the duties, and the scripts.                         |
| `uv run duty frontend_test` | The tests of the dashboard UI. Needs Node.                          |
| `uv run duty frontend_check` | The type check of the dashboard UI. Needs Node.                    |

The core and server suites each need 90% test coverage.

To run some of the Python tests by name, use `uv run duty test -k NAME --no-cov`. Without `--no-cov`, a subset of the tests fails the coverage limit.

To run every check in full, with no skips, set `GATE_CACHE_DISABLE=1`:

```sh
GATE_CACHE_DISABLE=1 uv run duty test
```

## Try a change by hand

When you run gate-cache or the dashboard on test data, use a temporary data directory. Your real stats then stay unchanged:

```sh
GATE_CACHE_DATA_DIR=/tmp/gc-dev GATE_CACHE_STATS=1 uv run gate-cache dashboard
```

## Work on the dashboard UI

Read `frontend/DESIGN.md` before you change the UI. It gives the color rules and tells you which shared component to use.

To see your changes with live reload, start the dashboard server, then start the Vite dev server in a second terminal:

```sh
uv run gate-cache dashboard --no-browser --port 7879
npm --prefix frontend run dev
```

The Vite dev server sends `/api` requests to port 7879.

## Work on the docs

The documentation site is in `docs/`, and [Zensical](https://zensical.org) builds it. To see your changes with live reload, run:

```sh
uv run duty docs
```

The site opens at `http://localhost:8010/gate-cache/`. `uv run duty docs_check` builds the site in strict mode, so a broken link fails. `uv run duty lint` runs it too. Each release publishes the site to GitHub Pages.

The site is for developers who add gate-cache to their projects. Write only what they need to install, use, configure, and troubleshoot gate-cache. `CHANGELOG.md` records the changes, so a page changes only when the change alters what the page tells the reader.

## Build the package

The wheel contains the built dashboard UI. To build the package and make sure that it contains the UI and the agent guides, run:

```sh
uv run duty frontend_build
uv build
uv run duty dist_check dist/*
```

## Send a change

- If your change alters a behavior, an option, or a message that the agent guides describe, update `src/gate_cache/agent/skill.md` or `prompt.md` in the same change.
- If your change alters something that the README or the docs describe, update them in the same change.
- Write each commit message and pull request title in the [Conventional Commits](https://www.conventionalcommits.org) format, such as `fix(status): show the scope of a gate with paths`. The commit-msg hook checks the format.
- Mark a change as breaking only when it breaks the CLI: a removed or renamed command or flag, a changed exit code, or a change to the output of the CLI. A change to the dashboard UI is never breaking.
- Open a pull request against `main`.
