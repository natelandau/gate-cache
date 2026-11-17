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
5. If a marker for the tree and the name exists, print a skip line and exit 0. If the marker records the run time of the command, the skip line shows it.
6. Run the command.
7. If the command exits 0 and the tree did not change during the run, write the marker. Otherwise, write a miss record that `gate-cache status` reports.

Every uncertain case runs the command. gate-cache can run a command that it did not need to run, but it skips a command only when a marker proves that the same gate passed on the same content.

Because the tree describes the working copy, a gate that passes on uncommitted work skips when you commit the same content. At commit time, prek and pre-commit stash unstaged edits, so the tree is the staged content that you commit. At push time with a clean checkout, the tree is the tree of `HEAD`.

The private index copy and its objects live in a temporary directory under `$XDG_RUNTIME_DIR/gate-cache`. If `XDG_RUNTIME_DIR` is not set, gate-cache uses the per-user runtime directory of the platform: `/run/user/<uid>/gate-cache` on Linux and `~/Library/Caches/TemporaryItems/gate-cache` on macOS. If `/run/user/<uid>` does not exist, as in many containers, gate-cache uses `runtime-<uid>/gate-cache` in the system temporary directory. gate-cache deletes each directory when it has the tree. A run that is killed can leave one behind, and the next run deletes it after one hour. If gate-cache cannot use this directory, the tree is unknown.

Git gives hooks `GIT_DIR` without `GIT_WORK_TREE`, and then treats the current directory as the top of the work tree. When the hook runs from a subdirectory, such as a module recipe, gate-cache finds the real work tree from `GIT_DIR` for its own git commands. The wrapped command gets the environment unchanged.

A command that exits 0 but changes the tree does not get a marker. Examples are a formatter that rewrites files and a command that leaves new untracked files. In this case, gate-cache prints `files changed during the run, not recording pass`.

## Gates scoped to paths

A gate with one or more `--path` options keys its marker on the content under those paths, not on the whole tree. The other rules above do not change. These rules apply to a scoped gate:

- Each value is a git pathspec. gate-cache matches it from the top of the work tree, whatever the current directory.
- gate-cache removes `GIT_LITERAL_PATHSPECS`, `GIT_GLOB_PATHSPECS`, `GIT_NOGLOB_PATHSPECS`, and `GIT_ICASE_PATHSPECS` from the environment of the match, so the same values match the same files in every environment.
- gate-cache sorts the values and removes duplicates. The order of the `--path` options has no effect on the key.
- gate-cache stages the working copy into the private index, as in step 2. It then lists the matched entries with `git ls-files --stage`. The list holds the mode, the blob hash, and the path of each tracked and untracked, non-ignored file under the paths.
- The scope is a hash of the sorted values and that list. [Marker format](#marker-format) gives the formula.
- If a path without `:(exclude)` or `:!` matches no file, or the paths select no file at all, gate-cache runs the command without the cache and writes no marker. The reason line names the path. This rule stops a typo in a path from giving a key that never changes.
- After a pass, gate-cache compares the scope, not the tree. An edit outside the paths during the run does not stop the marker.
- The checks in step 3 that make the tree unknown still examine the whole working copy. For example, a submodule with local changes outside the paths still makes gate-cache run the command without the cache.

A scoped marker and an unscoped marker never match each other, even with the same name.

## Arguments and exit codes

`--` is required, and only `--name` and `--path` can come before it, in any order. `--path` can occur more than once. gate-cache passes everything after `--` to the command without changes.

Without `--name`, the name of the gate is the command and its arguments, joined with spaces and quoted as Python `shlex.join` quotes them. An argument that holds a space or a shell special character gets single quotes, so `pytest 'a b'` and `pytest a b` are different names. Each set of arguments therefore has its own markers.

With `--name`, the name alone identifies the gate, and the arguments are not part of the key. A recipe such as `test *args` that gives `--name test` runs every variant under the same name, so a pass with `-k unit` writes the same marker as a pass of the full suite. To keep the variants apart, leave out `--name`, or put the arguments in the name.

| Situation                                                                             | Exit code                    |
| ------------------------------------------------------------------------------------- | ---------------------------- |
| The command ran                                                                       | The exit code of the command |
| A marker exists, so the command was skipped                                           | 0                            |
| A missing `--`, a `--name` or `--path` with no value, or another argument before `--` | 2, and nothing runs          |
| The command is not found                                                              | 127                          |
| The command cannot be run                                                             | 126                          |
| A signal stopped the command                                                          | 128 plus the signal number   |

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
- For a gate scoped with `--path`, every file outside its paths.

A change to one of these leaves the tree the same, so an existing marker still matches and gate-cache skips the command. A fresh run after such a change can give a different result. A CI runner that starts from a fresh clone has no markers and runs every command. A runner that keeps the `.git` directory between jobs also keeps the markers. If `CI` is on and `GATE_CACHE_DISABLE` is not set, gate-cache does not use them. `gate-cache clear` deletes the markers after you confirm, and `GATE_CACHE_DISABLE=1` runs every command without the cache. To make a gate depend on an ignored file, an environment variable, or a tool version, put its value in the gate name, as the README section [Inputs that git does not track](../README.md#inputs-that-git-does-not-track) shows.

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

A gate scoped with `--path` uses the same formula with a scope value in place of the tree hash. The scope value starts with `paths:`, so it never equals a tree hash:

```text
scope  = "paths:" + sha256_hex( "gate-cache-paths-v1" + "\0" + join(paths, "\0") + "\0\0" + listing )
key    = sha256( scope + "\0" + name )
```

`paths` holds the `--path` values, sorted by byte value, with duplicates removed. `listing` is the output of `git ls-files --stage -z` for those paths, run at the top of the work tree on the staged copy of the index. This shell snippet finds the marker of the `pytest` gate scoped to `src` and `tests`:

```bash
name=pytest
paths=(src tests) # sorted by byte value, with no duplicates
index=$(mktemp)
listing=$(mktemp)
cp -p "$(git rev-parse --git-path index)" "$index"
top=$(git rev-parse --show-toplevel)
(
  cd "$top" || exit 1
  unset GIT_LITERAL_PATHSPECS GIT_GLOB_PATHSPECS GIT_NOGLOB_PATHSPECS GIT_ICASE_PATHSPECS
  GIT_INDEX_FILE="$index" git add -A
  GIT_INDEX_FILE="$index" git ls-files --stage -z -- "${paths[@]}" >"$listing"
)
digest=$({
  printf 'gate-cache-paths-v1'
  printf '\0%s' "${paths[@]}"
  printf '\0\0'
  cat "$listing"
} | shasum -a 256 | cut -d' ' -f1)
rm -f "$index" "$listing"
key=$(printf '%s\0%s' "paths:$digest" "$name" | shasum -a 256 | cut -d' ' -f1)
marker="$(git rev-parse --git-common-dir)/gate-cache/$key"
```

The listing goes through a file because the shell drops NUL bytes from the output of `$(...)`.

The existence of the marker file is the signal. gate-cache writes a small JSON object with `tree`, `name`, `command`, `timestamp`, and `duration` keys. `duration` is the run time of the command in seconds, and the skip line and `gate-cache status --name` show it. gate-cache ignores a `duration` that is not a number from 0 to 30 days, and it does not read a marker that is larger than 16 MiB or is not a regular file. In these cases the skip line shows no saved time. A scoped gate writes its scope value in `tree`, and adds `paths`, the sorted path list, and `full_tree`, the tree of the whole working copy at the time of the run. `gate-cache status` without `--name` reads this JSON to list the gates, so it does not list a marker that another tool wrote without that content. Such a marker still makes its gate skip.

When a command fails, or exits 0 but changes the tree, gate-cache writes a miss record at `<key>.miss` in the same directory. The record holds the same JSON keys as a marker, except `duration`, plus `exit_code` and `reason`. A miss record never makes a gate skip. Only `gate-cache status` reads it, to list the missed gates. A pass of the same name on the same tree deletes the miss record. A run that a signal to gate-cache stopped, such as Ctrl-C, writes no miss record. Pruning and `gate-cache clear` delete miss records with the markers.

## Stats recording

When recording is on, each run of a gate adds one event to an inbox file. The inbox is `events.jsonl` in the data directory that `gate-cache stats` shows. gate-cache creates the data directory with mode 0700 and the inbox with mode 0600. Each event is one JSON line of at most 4096 bytes. If a line is longer, gate-cache first sets `host` to null. If the line is still too long, it sets `command` to null and sets `command_truncated`. If the line does not fit even without any paths, it sets `worktree`, `subdir`, `branch`, `remote`, `hook_stage`, and `reason` to null. If the line still does not fit, it sets `repo` to null when an empty name would not fit, then keeps the longest prefix of `name` that fits and sets `name_truncated`. Then it keeps the longest prefix of the `paths` list that fits and sets `paths_truncated`.

Recording never affects gating. It happens after the decision to skip or run, and a failure to record is silent. It cannot change a skip, an exit code, or the output of a gate. A run that a signal to gate-cache stopped, such as Ctrl-C, records no event.

### Event fields

Each event has these fields. A field is null when gate-cache does not know its value. All of them are in version 1 of the line format (`"v": 1`). Fields added later are optional, so a reader of version 1 must accept a line that has more fields or fewer.

| Field        | Value                                                                                                                         |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| `v`          | The line format version, `1`.                                                                                                 |
| `ts`         | The Unix time at which the run finished.                                                                                      |
| `id`         | A random ID for the event.                                                                                                    |
| `repo`       | The path of the git common directory of the repository.                                                                       |
| `name`       | The gate name.                                                                                                                |
| `tree`       | The tree key that the run used. Null when caching was off or the tree was unknown.                                            |
| `paths`      | The `--path` values.                                                                                                          |
| `outcome`    | What the run did. See [Outcomes](#outcomes).                                                                                  |
| `duration`   | The seconds that the command ran. Null for a skip.                                                                            |
| `saved`      | For a skip, the run time stored in the marker.                                                                                |
| `exit_code`  | The exit code of the command. Null for a skip.                                                                                |
| `reason`     | For an `uncached` run, why caching was off.                                                                                   |
| `version`    | The version of gate-cache that recorded the run.                                                                              |
| `trigger`    | What started the run: `ci` when `CI` is on, `hook` when `PRE_COMMIT` is on (pre-commit and prek set it for hooks), `agent` when a coding agent started the run, `terminal` when standard input is a terminal, else `other`. The first match applies. |
| `agent`      | For `agent`, the name of the agent: `claude-code` (`CLAUDECODE`), `gemini-cli` (`GEMINI_CLI`), or `codex` (`CODEX_THREAD_ID`). |
| `hook_stage` | For `hook`, the git hook stage from `PREK_HOOK_STAGE`, such as `pre-commit` or `pre-push`. pre-commit does not give the stage, so it is null for pre-commit. |
| `worktree`   | The path of the top of the working tree.                                                                                      |
| `subdir`     | The working directory relative to the top of the working tree, with `/` separators. `.` at the top.                          |
| `branch`     | The checked-out branch. Null when HEAD is detached.                                                                           |
| `head`       | The commit that HEAD points to.                                                                                               |
| `remote`     | The URL of the `origin` remote, or of the first remote in the git config when there is no `origin`, in the form `host/owner/repo`. gate-cache removes user names and credentials. A local path, or a URL that gate-cache cannot parse without a risk of keeping a credential, gives null. A short alias from a git `insteadOf` rule, such as `gh:owner/repo`, also gives null, because the alias does not name the real host. Later versions can use it to join separate clones of one project. |
| `machine`    | A random ID that gate-cache creates on the first recorded run and stores in `machine-id` in the data directory. It is the stable key for the machine. |
| `host`       | The host name of the machine. It is a label, and it can change.                                                               |
| `platform`   | The platform, as Python's `sys.platform` gives it, such as `darwin` or `linux`.                                               |
| `overhead`   | The seconds that gate-cache used to find the tree key and look up the marker. Null when caching was off.                      |
| `marker_age` | For a skip, the seconds since gate-cache wrote the marker.                                                                    |
| `cpu`        | The user and system CPU seconds of the command. Null for a skip.                                                              |
| `max_rss`    | The peak memory of the command in bytes. It is the peak of all commands that the gate-cache process ran. Null for a skip.     |
| `command`    | The command line, when `--name` gives a name that is not the command line. Null otherwise, because the name is then the command line. |

gate-cache reads these values from files and the environment, and it runs no extra git command to get them. The one exception is `repo` for a run without the cache, which needs one git command. When recording is off, gate-cache does none of this work.

### Outcomes

Each event has one outcome:

| Outcome           | Meaning                                                                                  |
| ----------------- | ---------------------------------------------------------------------------------------- |
| `skip`            | A marker matched, so the command did not run. `saved` holds the duration in the marker.  |
| `pass`            | The command exited 0 and gate-cache wrote a marker.                                      |
| `pass_unrecorded` | The command exited 0, but gate-cache recorded no pass. The run changed the tree, or gate-cache could not check the tree. |
| `fail`            | The command exited with a code other than 0.                                             |
| `uncached`        | The command ran without the cache. `reason` holds the printed cause, such as caching turned off by `CI` or `GATE_CACHE_DISABLE`, or an unknown tree. |

`saved` is empty for a skip whose marker has no valid `duration`.

### Inbox and archive

The dashboard moves events from the inbox into an archive, a SQLite file named `stats.sqlite3` in the data directory. It ingests once at start and then once a second while it runs. For each ingest, it renames the live inbox to `events.<number>.processing`. It reads a renamed file after 2 seconds, so a gate that still writes to the old file finishes first. It skips a line that is not valid, and it ignores a line that it already stored. The archive keeps the full text of each line, so a later version of gate-cache can use fields that an earlier version recorded. An event with an outcome that this version does not know, written by a newer version, stays in the archive, but the dashboard does not count it. When no dashboard runs, events wait in the inbox until the next dashboard start. The archive keeps events for 365 days, and each ingest that adds events deletes older ones.

`gate-cache stats clear` deletes the inbox, the renamed files, the archive, and any `.machine-id.*` temporary files that an interrupted run left. It keeps `machine-id`, so the machine keeps its ID. It takes the dashboard lock before it asks for confirmation, so it refuses at once when a dashboard runs, and no dashboard can start while the prompt waits for an answer.

### Metrics

The dashboard computes its numbers from the archive, for the repository and the time range that you choose:

- Runs: every recorded event, including `uncached` events.
- Time saved: the sum of `saved` over `skip` events. A skip with no `saved` adds nothing, and the dashboard counts these skips separately.
- Skip rate: `skip` events divided by the events in which a gate checked its cache: `skip`, `pass`, `pass_unrecorded`, and `fail`. `uncached` events are not part of it.
- Average and median run time: the `duration` of `pass` events.
- Flaky gate: a gate that has, for one tree key, both a `fail` event and a `pass` or `pass_unrecorded` event. The same content both failed and passed, so the result is not stable. The dashboard lists the trees and the runs for each.

Days start and end in the time zone of your browser.
