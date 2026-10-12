# gate-cache

Skip a command that already passed on the same code.

A lint or test command often runs many times on code that did not change. It runs when you finish the work, in a pre-commit hook, after a rebase that changed nothing, and in a pre-push hook. When an agent works in the repository, it runs the same command again. If the command takes minutes, the repeat runs take most of the time between finished code and a pushed branch.

gate-cache remembers which commands passed on which code. It wraps a command and gives it a name. When the command passes, gate-cache writes a marker for that name and for the exact content of the tracked files. The next time the same name runs on the same content, gate-cache finds the marker, skips the command, and exits 0 at once.

```console
$ gate-cache --name pytest -- uv run pytest
============================= 412 passed in 94.20s =============================

$ gate-cache --name pytest -- uv run pytest
gate-cache: pytest already passed on tree aaff74984ccc, skipping
```

A change to a tracked file changes the content, so no marker matches and the command runs again. CI starts from a fresh clone with no markers, so CI runs every command.

## Install

gate-cache requires Python 3.11 or later, on macOS or Linux.

```sh
uv tool install gate-cache
```

The prek and pre-commit hooks install gate-cache themselves, so the hooks work without this step.

## Run a command through gate-cache

The name goes after `--name`, and the command goes after `--`:

```sh
gate-cache --name pytest -- uv run pytest
gate-cache --name ruff -- uv run ruff check .
```

Each name has its own markers. A command run under one name never skips because of a marker for another name.

gate-cache exits with the exit code of the command, or with 0 when it skips the command. It writes a marker only when the command passes, so a command that failed runs again the next time.

When the working copy has uncommitted edits or files that git does not track, the content on disk is not a commit-ready snapshot. gate-cache then runs the command and writes no marker.

## Run it as a hook

gate-cache works with [prek](https://github.com/j178/prek) and with [pre-commit](https://pre-commit.com) 3.2 or later. Each `gate-cache` hook takes the same arguments as the command line:

```yaml
repos:
  - repo: https://github.com/natelandau/gate-cache
    rev: v0.1.0
    hooks:
      - id: gate-cache
        name: pytest
        args: [--name, pytest, --, uv, run, pytest]
        files: ^(src/|tests/)
      - id: gate-cache
        name: ruff
        args: [--name, ruff, --, uv, run, ruff, check, .]
```

The hook runs at commit time and at push time. At commit time, gate-cache matches the content that you commit.

The hook runs in its own virtual environment, and the wrapped command inherits that environment. A command started with `uv run`, or a project command such as `just test`, runs in the project environment. `uv run` prints a warning that `VIRTUAL_ENV` does not match the project. The warning has no effect on the run.

Hooks, agents, and your terminal all read and write the same markers. When one of them runs `gate-cache --name pytest -- uv run pytest` and it passes, the others skip that name on the same content.

## Examples

These examples show gate-cache inside the task runner of a project. When a recipe holds the wrapped command, everything that runs the recipe uses the same name and the same markers.

### justfile

```just
test:
    gate-cache --name test -- uv run pytest

lint:
    gate-cache --name lint -- uv run ruff check .
```

After `just test` passes, the next `just test` on the same content skips pytest.

### Makefile

```make
test:
	gate-cache --name test -- uv run pytest

lint:
	gate-cache --name lint -- uv run ruff check .
```

### A hook that calls the recipe

A local hook can run the recipe instead of the gate-cache hook repository:

```yaml
repos:
  - repo: local
    hooks:
      - id: test
        name: test
        entry: just test
        language: system
        pass_filenames: false
        stages: [pre-commit, pre-push]
```

With this hook, a commit, a push, an agent, and your terminal all run `just test` and share its markers. The recipe runs in the project environment, so `uv run` prints no `VIRTUAL_ENV` warning. This form needs `gate-cache` and `just` on the `PATH`.

## See what already passed

`gate-cache status` lists every name that passed on the current content:

```console
$ gate-cache status
  tree:  aaff74984cccd156a469afa7d9ab10e4777beb24
  gates: pytest, ruff
```

With `--name`, it reports on one name:

```console
$ gate-cache status --name pytest
  name:   pytest
  tree:   aaff74984cccd156a469afa7d9ab10e4777beb24
  marker: /path/to/repo/.git/gate-cache/698af5f62774dab7babf59a4b8969fed12d8668428cee49ca89baf4aa392de6d
  result: hit
```

`status` runs nothing. It exits 0 when a marker matches and 1 when none does. When gate-cache cannot match the content, for example because of uncommitted edits, the `tree` line gives the reason.

## Start fresh

A marker records only the content of the tracked files. A new tool version, a changed environment variable, or a change to a service does not change that content, so the old markers still match.

`gate-cache clear` deletes every marker for the repository:

```console
$ gate-cache clear
gate-cache: removed 3 markers
```

`GATE_CACHE_DISABLE=1` runs every command without the cache, for one command or for a whole session:

```sh
GATE_CACHE_DISABLE=1 git push
```

## Settings

Two environment variables control gate-cache.

| Variable                  | Effect                                                     | Default |
| ------------------------- | ---------------------------------------------------------- | ------- |
| `GATE_CACHE_DISABLE`      | Any value that is not empty and not `0` turns off caching. | not set |
| `GATE_CACHE_MAX_AGE_DAYS` | gate-cache deletes markers older than this number of days. | `30`    |

Each marker is one small file in the `.git` directory of the repository, so all worktrees of the repository share the markers.

## Learn more

- [How gate-cache works](docs/how-it-works.md) describes the exact rules for a skip, what a marker covers, and the marker format for tools that read markers directly.
- `gate-cache --help` gives the full command reference.
