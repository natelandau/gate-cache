# gate-cache

Skip lint and test gates that already passed on the exact same git tree.

The same code often goes through the same gates many times before it ships: at the end of local work, in a pre-commit hook, again after a rebase that changed nothing, and again in a pre-push hook. When a test suite takes minutes, this repetition is the slowest part of the cycle.

gate-cache wraps one gate command. When the command passes, gate-cache records the pass against the git tree of the tracked files. If you run the same named gate on the same tree again, gate-cache exits 0 in milliseconds and does not run the command. CI starts from a fresh clone with no records, so CI still runs every gate.

```console
$ gate-cache --name pytest -- uv run pytest
... pytest output ...
$ gate-cache --name pytest -- uv run pytest
gate-cache: pytest already passed on tree aaff74984ccc, skipping
```

## Install

gate-cache requires Python 3.11 or later.

To install the command line tool, run:

```sh
uv tool install gate-cache
```

You do not need to install anything to use gate-cache as a hook. [prek](https://github.com/j178/prek) and [pre-commit](https://pre-commit.com) 3.2 or later install it from the hook repository.

## Use it as a hook

Add one `gate-cache` entry for each gate that you want to cache. Each entry gives the gate a name with `--name` and puts the command after `--`:

```yaml
repos:
  - repo: https://github.com/natelandau/gate-cache
    rev: v0.1.0
    hooks:
      - id: gate-cache
        name: pytest
        alias: pytest
        args: [--name, pytest, --, uv, run, pytest]
        files: ^(src/|tests/|uv\.lock|pyproject\.toml)
      - id: gate-cache
        name: ruff
        alias: ruff
        args: [--name, ruff, --, uv, run, ruff, check, .]
```

The hook sets `pass_filenames: false`, so the runner does not append file names to the wrapped command. The `files` and `always_run` keys are your choice. The hook runs in the `pre-commit`, `pre-push`, and `manual` stages.

The wrapped command runs in the environment of the hook. prek and pre-commit install gate-cache in its own virtual environment, so the command sees `VIRTUAL_ENV` set to that environment, and the `bin` directory of that environment comes first on `PATH`. gate-cache does not change this environment. Thus:

- Start the command with `uv run`, or give an absolute path or a command that your project supplies. Do not use a bare tool name such as `pytest`, because it can find the copy in the hook environment, or find nothing.
- `uv run` prints `VIRTUAL_ENV=... does not match the project environment path .venv and will be ignored`. This warning is harmless: `uv run` uses the project environment.

Agents, scripts, and people can call the same command directly. A pass that one caller records is a hit for every other caller:

```sh
gate-cache --name pytest -- uv run pytest
```

Both `--name` and `--` are required, and only `--name` can come before `--`. gate-cache passes everything after `--` to the command without changes. A missing `--name` or `--`, or any other argument before `--`, is a usage error: gate-cache runs nothing and exits 2. Otherwise gate-cache exits with the exit code of the command, or 0 on a skip. If a signal stops the command, gate-cache exits with 128 plus the signal number.

## Never wrap these

gate-cache keys a pass only on the content of tracked files. Never wrap a command whose result depends on anything else. A wrapped check of that kind can be skipped when a fresh run fails.

Keep these as normal, unwrapped hooks:

- Commit message checks, such as the commitizen `commit-msg` hook.
- Branch name checks.
- Any command that talks to a remote.
- Secret scanners and other hooks that must always run, such as gitleaks.

gate-cache decides only about the command that it wraps. It never skips other hooks.

## How a cache hit is decided

Each time it runs, gate-cache does these steps in this sequence:

1. If `GATE_CACHE_DISABLE` turns caching off, run the command and record nothing.
2. Find the tree to key on. The tree is `git write-tree`, which is the content of the index. gate-cache uses it only if the tracked files in the working copy match the index and no untracked, non-ignored files exist.
3. If the tree is unknown, run the command without the cache and record nothing. The tree is unknown with unstaged changes, untracked non-ignored files, an unmerged index, outside a git repository, or after any git error.
4. If git cannot find the git directory that holds the markers, run the command without the cache and record nothing.
5. If a marker for the tree and name exists, print a skip line and exit 0.
6. Run the command.
7. If the command exits 0 and the tree is still the same, write the marker.

At commit time, prek and pre-commit stash unstaged edits, so the key is the staged content that you commit. At push time with a clean checkout, the key is the tree of `HEAD`.

A command that exits 0 but changes the tree does not get a record. Examples are a formatter that rewrites files and a command that leaves new untracked files. gate-cache prints `files changed during the run, not recording pass` in this case.

A failing command, a signal, or Ctrl-C never writes a marker. If gate-cache gets `SIGTERM` or `SIGHUP` while the command runs, it sends the signal to the command, waits for the command to stop, and exits with the status of the command. A cache error never changes the exit code of the command. If gate-cache cannot write a marker, it prints a warning and keeps the exit code.

Markers live in the git common directory, so all linked worktrees of a repository share them. After each new marker, gate-cache deletes markers older than 30 days.

## Marker format

Other tools can read and write markers without calling gate-cache. The marker format is a public contract, and any change to it is a breaking change.

The key is the lowercase hex SHA-256 of the tree hash, a NUL byte, and the gate name:

```text
key    = sha256( tree_hash + "\0" + name )
marker = $(git rev-parse --git-common-dir)/gate-cache/<key>
```

To find the marker for the `pytest` gate from a shell, run:

```bash
tree=$(git write-tree)
key=$(printf '%s\0%s' "$tree" pytest | shasum -a 256 | cut -d' ' -f1)
marker="$(git rev-parse --git-common-dir)/gate-cache/$key"
```

On Linux systems without `shasum`, use `sha256sum` instead.

The existence of the marker file is the signal. The file holds a small JSON object with `tree`, `name`, `command`, and `timestamp` keys for debugging. Do not depend on its content.

## Blind spots

The key covers only the content and the modes of tracked files. It does not cover:

- Ignored inputs, such as `.env` and `.venv`.
- Environment variables.
- Tool versions that a lockfile does not pin.
- External services.
- Changes that git is told to ignore. `core.fileMode=false` hides changes to the executable bit. `git update-index --assume-unchanged` and `--skip-worktree` hide edits to tracked files.
- Changes in submodules that git is told to ignore. `diff.ignoreSubmodules` and the `submodule.<name>.ignore` setting can hide a dirty submodule, so a run with uncommitted submodule edits can record a pass for the tree of the parent repository.

If a gate depends on one of these, gate-cache can skip it when a fresh run fails. CI still runs every gate from a fresh clone. After a change outside git, such as a tool upgrade, run `gate-cache clear`. To run gates without the cache, set `GATE_CACHE_DISABLE=1`.

## Commands

gate-cache has two commands in addition to the default run. Run `gate-cache --help` for the full reference.

### status

`gate-cache status` reports whether a gate would skip on the current tree. It runs nothing.

```console
$ gate-cache status --name pytest
  name:   pytest
  tree:   aaff74984cccd156a469afa7d9ab10e4777beb24
  marker: /path/to/repo/.git/gate-cache/698af5f62774dab7babf59a4b8969fed12d8668428cee49ca89baf4aa392de6d
  result: hit
```

If the tree is unknown, the `tree` line gives the reason, such as `unknown: untracked file: notes.txt`. The command exits 0 on a hit and 1 otherwise.

### clear

`gate-cache clear` deletes every marker for the current repository, in all of its worktrees. Use it after a change that git cannot see, such as a tool upgrade. Outside a git repository, it exits 1.

```console
$ gate-cache clear
gate-cache: removed 3 markers
```

## Turn off caching

If `GATE_CACHE_DISABLE` has a value that is not empty and not `0`, gate-cache runs every command and never reads or writes markers. With caching off, `gate-cache status` exits 1.

```sh
GATE_CACHE_DISABLE=1 git push
```

## Supported runners and platforms

gate-cache works with prek and with pre-commit 3.2 or later. It runs on macOS and Linux. Windows is not supported.
