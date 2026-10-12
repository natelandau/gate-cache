# How gate-cache works

This page describes the exact rules that gate-cache uses: when it skips a command, what a marker covers, and the marker format that other tools can read and write. The [README](../README.md) covers everyday use.

## When gate-cache skips a command

gate-cache keys each marker on two values: the gate name and the git tree of the tracked files. The tree is the output of `git write-tree`, which is the content of the index. It covers the path, the bytes, and the mode of each tracked file.

Each time it runs, gate-cache does these steps in this sequence:

1. If `GATE_CACHE_DISABLE` turns caching off, run the command and write no marker.
2. Find the tree. gate-cache uses `git write-tree` only if the tracked files in the working copy match the index and no untracked, non-ignored files exist.
3. If the tree is unknown, run the command without the cache and write no marker. The tree is unknown with unstaged changes, untracked non-ignored files, an unmerged index, outside a git repository, or after any git error.
4. If git cannot find the git directory that holds the markers, run the command without the cache and write no marker.
5. If a marker for the tree and the name exists, print a skip line and exit 0.
6. Run the command.
7. If the command exits 0 and the tree did not change during the run, write the marker.

Every uncertain case runs the command. gate-cache can run a command that it did not need to run, but it skips a command only when a marker proves that the same gate passed on the same content.

At commit time, prek and pre-commit stash unstaged edits, so the tree is the staged content that you commit. At push time with a clean checkout, the tree is the tree of `HEAD`.

A command that exits 0 but changes the tree does not get a marker. Examples are a formatter that rewrites files and a command that leaves new untracked files. In this case, gate-cache prints `files changed during the run, not recording pass`.

## Arguments and exit codes

Both `--name` and `--` are required, and only `--name` can come before `--`. gate-cache passes everything after `--` to the command without changes.

The name alone identifies the command. A recipe such as `test *args` that passes extra arguments to the wrapped command runs every variant under the same name, so a pass with `-k unit` writes the same marker as a pass of the full suite.

| Situation                                                   | Exit code                    |
| ----------------------------------------------------------- | ---------------------------- |
| The command ran                                             | The exit code of the command |
| A marker exists, so the command was skipped                 | 0                            |
| A missing `--name` or `--`, or another argument before `--` | 2, and nothing runs          |
| The command is not found                                    | 127                          |
| The command cannot be run                                   | 126                          |
| A signal stopped the command                                | 128 plus the signal number   |

A failing command, a signal, or Ctrl-C never writes a marker. If gate-cache gets `SIGTERM` or `SIGHUP` while the command runs, it sends the signal to the command, waits for the command to stop, and exits with the status of the command. A signal that the shell ignores, for example under `nohup`, stays ignored for the command.

A cache error never changes the exit code of the command. If gate-cache cannot write a marker, it prints a warning and keeps the exit code.

## The hook environment

prek and pre-commit install gate-cache in its own virtual environment. The wrapped command inherits that environment: `VIRTUAL_ENV` points to it, and its `bin` directory comes first on `PATH`. gate-cache does not change the environment of the command.

A bare tool name such as `pytest` resolves in that environment first, so it finds the copy in the hook environment, or finds nothing. A command started with `uv run`, an absolute path, or a project command such as `just test` runs in the project environment. `uv run` prints `VIRTUAL_ENV=... does not match the project environment path .venv and will be ignored`, and then uses the project environment.

A local hook with `language: system` runs gate-cache from the `PATH` of the developer instead, so the command starts in the project environment with no warning:

```yaml
repos:
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: gate-cache --name pytest -- uv run pytest
        language: system
        pass_filenames: false
```

This form needs `gate-cache` on the `PATH` of each developer.

## What a marker covers

A marker covers the name and the tree, and nothing else. The tree holds the content and the modes of tracked files. A marker does not cover:

- Ignored inputs, such as `.env` and `.venv`.
- Environment variables.
- Tool versions that a lockfile does not pin.
- External services.
- Changes that git is told to ignore. `core.fileMode=false` hides changes to the executable bit. `git update-index --assume-unchanged` and `--skip-worktree` hide edits to tracked files.
- Changes in submodules that git is told to ignore. `diff.ignoreSubmodules` and the `submodule.<name>.ignore` setting can hide a dirty submodule.

A change to one of these leaves the tree the same, so an existing marker still matches and gate-cache skips the command. A fresh run after such a change can give a different result. A CI runner that starts from a fresh clone has no markers and runs every command. A runner that keeps the `.git` directory between jobs also keeps the markers. `gate-cache clear` deletes the markers, and `GATE_CACHE_DISABLE=1` runs every command without the cache.

A marker also does not cover the commit message, the branch name, or anything on a remote. gate-cache decides only about the command that it wraps, and it never skips other hooks.

## Marker lifetime

Markers live in the git common directory, so all linked worktrees of a repository share them. Each time gate-cache writes a marker, it deletes every marker older than `GATE_CACHE_MAX_AGE_DAYS`, which is 30 by default. The age counts from when gate-cache wrote the marker. A skip does not reset it, so a marker that a gate hits every day still expires.

`GATE_CACHE_MAX_AGE_DAYS` takes a positive whole number. For any other value, gate-cache prints a warning and uses 30.

## Marker format

Other tools can read and write markers without calling gate-cache. The marker format is a public contract, and any change to it is a breaking change.

The marker key is the lowercase hex SHA-256 of the tree hash, a NUL byte, and the gate name:

```text
key    = sha256( tree_hash + "\0" + name )
marker = $(git rev-parse --git-common-dir)/gate-cache/<key>
```

This shell snippet finds the marker for the `pytest` name:

```bash
tree=$(git write-tree)
key=$(printf '%s\0%s' "$tree" pytest | shasum -a 256 | cut -d' ' -f1)
marker="$(git rev-parse --git-common-dir)/gate-cache/$key"
```

On Linux systems without `shasum`, `sha256sum` gives the same digest.

The existence of the marker file is the signal. gate-cache writes a small JSON object with `tree`, `name`, `command`, and `timestamp` keys. `gate-cache status` without `--name` reads this JSON to list the gates, so it does not list a marker that another tool wrote without that content. Such a marker still makes its gate skip.
