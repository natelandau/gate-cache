# How gate-cache works

This page describes the exact rules that gate-cache uses: when it skips a command, what a marker covers, and the marker format that other tools can read and write. The [README](../README.md) covers everyday use.

## When gate-cache skips a command

gate-cache keys each marker on two values: the gate name and the git tree of the files that the command reads. The tree is the git tree hash that a commit of the working copy gets. It covers the path, the bytes, and the mode of each tracked file and each untracked, non-ignored file. Ignored files are not in the tree.

Each time it runs, gate-cache does these steps in this sequence:

1. If caching is off, run the command and write no marker. If `GATE_CACHE_DISABLE` has a value, it decides. If it is empty or not set, `CI` decides. Each variable turns off caching when its value is not empty, `0`, or `false`, in any case.
2. Find the tree. The tree is the tree that `git add -A` followed by `git write-tree` gives. When the working copy matches the index, this is the tree of the index. gate-cache runs both commands on a private copy of the index, so it never changes your index, never stages a file, and never adds files to `.git/objects`. Clean filters, such as Git LFS, still run and can write to their own stores, as they do when you stage a file.
3. If the tree is unknown, run the command without the cache and write no marker. The tree is unknown in these cases:
    - An unmerged index, outside a git repository, or after any git error.
    - A file that `git add -A` cannot stage, such as a nested git repository that has no commit. The reason line shows the error from git.
    - An index entry with `--assume-unchanged` or `--skip-worktree`. Sparse checkout sets `--skip-worktree`.
    - A submodule or a nested git repository that has local changes, untracked files, or a checked-out commit that is different from the commit in the index. gate-cache examines each submodule directly, at every level, so `diff.ignoreSubmodules`, `submodule.<name>.ignore`, and the submodule's own `status.showUntrackedFiles` cannot hide a change.
    - A submodule that is not checked out, such as an uninitialized submodule. `git submodule update --init` fills its directory but does not change the tree. To use the cache, initialize the submodule.
    - A submodule directory that holds files but is not a git repository.
    - On a case-insensitive filesystem, a file that differs from its index entry only by the case of its name.
4. If git cannot find the git directory that holds the markers, run the command without the cache and write no marker.
5. If a marker for the tree and the name exists, print a skip line and exit 0.
6. Run the command.
7. If the command exits 0 and the tree did not change during the run, write the marker. Otherwise, write a miss record that `gate-cache status` reports.

Every uncertain case runs the command. gate-cache can run a command that it did not need to run, but it skips a command only when a marker proves that the same gate passed on the same content.

Because the tree describes the working copy, a gate that passes on uncommitted work skips when you commit the same content. At commit time, prek and pre-commit stash unstaged edits, so the tree is the staged content that you commit. At push time with a clean checkout, the tree is the tree of `HEAD`.

The private index copy and its objects live in a temporary directory under `$XDG_RUNTIME_DIR/gate-cache`. If `XDG_RUNTIME_DIR` is not set, gate-cache uses the per-user runtime directory of the platform: `/run/user/<uid>/gate-cache` on Linux and `~/Library/Caches/TemporaryItems/gate-cache` on macOS. If `/run/user/<uid>` does not exist, as in many containers, gate-cache uses `runtime-<uid>/gate-cache` in the system temporary directory. gate-cache deletes each directory when it has the tree. A run that is killed can leave one behind, and the next run deletes it after one hour. If gate-cache cannot use this directory, the tree is unknown.

Git gives hooks `GIT_DIR` without `GIT_WORK_TREE`, and then treats the current directory as the top of the work tree. When the hook runs from a subdirectory, such as a module recipe, gate-cache finds the real work tree from `GIT_DIR` for its own git commands. The wrapped command gets the environment unchanged.

A command that exits 0 but changes the tree does not get a marker. Examples are a formatter that rewrites files and a command that leaves new untracked files. In this case, gate-cache prints `files changed during the run, not recording pass`.

## Arguments and exit codes

`--` is required, and only `--name` can come before it. gate-cache passes everything after `--` to the command without changes.

Without `--name`, the name of the gate is the command and its arguments, joined with spaces and quoted as Python `shlex.join` quotes them. An argument that holds a space or a shell special character gets single quotes, so `pytest 'a b'` and `pytest a b` are different names. Each set of arguments therefore has its own markers.

With `--name`, the name alone identifies the gate, and the arguments are not part of the key. A recipe such as `test *args` that gives `--name test` runs every variant under the same name, so a pass with `-k unit` writes the same marker as a pass of the full suite. To keep the variants apart, leave out `--name`, or put the arguments in the name.

| Situation                                                                 | Exit code                    |
| ------------------------------------------------------------------------- | ---------------------------- |
| The command ran                                                           | The exit code of the command |
| A marker exists, so the command was skipped                               | 0                            |
| A missing `--`, a `--name` with no value, or another argument before `--` | 2, and nothing runs          |
| The command is not found                                                  | 127                          |
| The command cannot be run                                                 | 126                          |
| A signal stopped the command                                              | 128 plus the signal number   |

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
        entry: gate-cache -- uv run pytest
        language: system
        pass_filenames: false
```

This form needs `gate-cache` on the `PATH` of each developer.

## What a marker covers

A marker covers the name and the tree, and nothing else. The tree holds the content and the modes of every file that git does not ignore. A marker does not cover:

- Ignored inputs, such as `.env` and `.venv`.
- Environment variables.
- Tool versions that a lockfile does not pin.
- External services.
- The working directory. `ruff check .` checks different files in `src/` than at the top of the repository, but both runs have the same tree and the same name. Run such a command from one directory, or give each directory its own `--name`.
- Changes to the executable bit when `core.fileMode=false` is set.
- Differences that a clean filter removes before git hashes a file, such as line endings with `core.autocrlf` or the content behind a Git LFS pointer when the pointer does not change.

A change to one of these leaves the tree the same, so an existing marker still matches and gate-cache skips the command. A fresh run after such a change can give a different result. A CI runner that starts from a fresh clone has no markers and runs every command. A runner that keeps the `.git` directory between jobs also keeps the markers. If `CI` is on and `GATE_CACHE_DISABLE` is not set, gate-cache does not use them. `gate-cache clear` deletes the markers, and `GATE_CACHE_DISABLE=1` runs every command without the cache. To make a gate depend on an ignored file, an environment variable, or a tool version, put its value in the gate name, as the README section [Inputs that git does not track](../README.md#inputs-that-git-does-not-track) shows.

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

The name is the value of `--name`, or the quoted command line when `--name` is not given. The tree hash is the tree from step 2 of [When gate-cache skips a command](#when-gate-cache-skips-a-command). This shell snippet computes it on a copy of the index, then finds the marker for the `pytest` name:

```bash
index=$(mktemp)
cp -p "$(git rev-parse --git-path index)" "$index"
GIT_INDEX_FILE="$index" git add -A
tree=$(GIT_INDEX_FILE="$index" git write-tree)
rm -f "$index"
key=$(printf '%s\0%s' "$tree" pytest | shasum -a 256 | cut -d' ' -f1)
marker="$(git rev-parse --git-common-dir)/gate-cache/$key"
```

If the working copy matches the index and has no untracked, non-ignored files, `git write-tree` alone gives the same tree. The snippet writes objects for new content into `.git/objects`, as `git add` does. On Linux systems without `shasum`, `sha256sum` gives the same digest.

The existence of the marker file is the signal. gate-cache writes a small JSON object with `tree`, `name`, `command`, and `timestamp` keys. `gate-cache status` without `--name` reads this JSON to list the gates, so it does not list a marker that another tool wrote without that content. Such a marker still makes its gate skip.

When a command fails, or exits 0 but changes the tree, gate-cache writes a miss record at `<key>.miss` in the same directory. The record holds the same JSON keys as a marker, plus `exit_code` and `reason`. A miss record never makes a gate skip. Only `gate-cache status` reads it, to list the missed gates. A pass of the same name on the same tree deletes the miss record. A run that a signal to gate-cache stopped, such as Ctrl-C, writes no miss record. Pruning and `gate-cache clear` delete miss records with the markers.
