# gate-cache

Skip a command that already passed on the same code.

A lint or test command often runs many times on code that did not change. It runs when you finish the work, in a pre-commit hook, after a rebase that changed nothing, and in a pre-push hook. When an agent works in the repository, it runs the same command again. If the command takes minutes, the repeat runs take most of the time between finished code and a pushed branch.

gate-cache remembers which commands passed on which code. It wraps a command, and the command line is the name of the gate. When the command passes, gate-cache writes a marker for that name and for the exact content of the files in the working copy that git does not ignore. The next time the same name runs on the same content, gate-cache finds the marker, skips the command, and exits 0 at once.

```console
$ gate-cache -- uv run pytest
============================= 412 passed in 94.20s =============================

$ gate-cache -- uv run pytest
gate-cache: uv run pytest already passed on tree aaff74984ccc, skipping (saved 1m 34s)
```

The time in parentheses is how long the command ran when it passed, so the time that the skip saves is approximate.

A change to any file that git does not ignore changes the content, so no marker matches and the command runs again. To make a gate match only the files that its command reads, [scope the gate to its paths](#scope-a-gate-to-its-paths). A CI runner that starts from a fresh clone has no markers, so it runs every command.

## Install

gate-cache requires Python 3.11 or later, on macOS or Linux.

```sh
uv tool install gate-cache
```

The prek and pre-commit hooks install gate-cache themselves, so the hooks work without this step. In a project without Python tooling, `uvx gate-cache` runs gate-cache without an install.

## Add gate-cache to a project with an agent

A coding agent can add gate-cache to a project in any language. Open an agent session at the top of the repository and give it this prompt:

```text
Run `uvx gate-cache --prompt` and follow the instructions that it prints.
```

The agent reads the guide that gate-cache prints and asks you which commands to wrap, how to install gate-cache, which gates to scope to their paths, and whether git hooks run the gates. Then it wraps the commands, makes sure that each gate works, and stops before it commits. The instructions always match the version of gate-cache that the agent runs.

Two flags print text for agents:

- `gate-cache --prompt` prints the setup task that the agent follows.
- `gate-cache --skill` prints the guide for an agent that works in a repository that uses gate-cache. The output is a `SKILL.md` file. To give it to Claude Code in every session, save it as a skill:

```sh
mkdir -p ~/.claude/skills/gate-cache
gate-cache --skill > ~/.claude/skills/gate-cache/SKILL.md
```

Run the second command again after you upgrade gate-cache. `gate-cache --help` tells agents to run `gate-cache --skill`, so an agent without the saved skill also finds the guide.

## Run a command through gate-cache

The command goes after `--`:

```sh
gate-cache -- uv run pytest
gate-cache -- uv run ruff check .
```

The command and its arguments are the name of the gate. Each name has its own markers, so a pass of `uv run pytest -k unit` never skips `uv run pytest`.

To choose the name yourself, put `--name` before `--`:

```sh
gate-cache --name pytest -- uv run pytest
```

With `--name`, the name alone identifies the gate, and the arguments of the command are not part of it. Give a name when two different command lines do the same check and must share markers, or when a gate depends on [inputs that git does not track](#inputs-that-git-does-not-track).

gate-cache exits with the exit code of the command, or with 0 when it skips the command. It writes a marker only when the command passes, so a command that failed runs again the next time.

The tree includes uncommitted edits and untracked files that git does not ignore. A gate that passes on uncommitted work therefore skips in the commit hook when you commit the same content. gate-cache computes the tree from a private copy of the index, so it never stages files or changes your index.

## Run the same gate twice at once

If a run finds another run of the same gate in progress on the same content, it waits. The two runs have the same name and the same tree, and they can be in different worktrees of the repository. The waiting run prints a line that names the worktree of the other run and its age:

```console
$ gate-cache -- uv run pytest
gate-cache: uv run pytest is running in /work/app-feature (started 1m 12s ago), waiting
gate-cache: uv run pytest already passed on tree aaff74984ccc, skipping (saved 1m 34s)
```

The wait is not a hang. When the other run ends, gate-cache checks the content again. If the other run passed, the waiting run skips. Otherwise it runs the command.

A run waits at most 15 minutes in total. After that, gate-cache prints `running anyway` and runs the command. [Settings](#settings) shows how to change the limit and how to report the failure of the other run instead of running again. Waiting works on macOS and Linux.

## Scope a gate to its paths

In a repository with several parts, a change to the docs or to one part does not change the result of the tests of another part. A gate that has `--path` options matches only the content under those paths:

```sh
gate-cache --name api-test --path api/ --path uv.lock -- uv run pytest api/tests
```

After this gate passes, a change to `README.md` or to `web/` lets it skip, and so does a rebase that brings in only those changes. A change under `api/` or to `uv.lock` makes it run again.

Each `--path` is a git pathspec. gate-cache reads it from the top of the repository, so a recipe that runs in a subdirectory and a hook that runs at the top give the same paths. A directory covers every file under it. The order of the paths has no effect. Wildcards and `:(exclude)` work:

```sh
gate-cache --name scripts-test --path scripts/ --path ':(exclude)scripts/fixtures/' -- uv run pytest scripts
```

In a pathspec, `*` also matches `/`, so `*.just` matches a `.just` file in every directory. `**/justfile` matches only a `justfile` inside a directory. To also match the `justfile` at the top, use `:(glob)**/justfile`.

> **Warning:** List every file and directory that the command reads, including lock files and shared config. The gate skips when nothing under its paths changed. A change to a file outside the paths does not make the gate run again.

If a path matches no file, gate-cache runs the command without the cache and prints that path. A typo in a path therefore never makes a gate skip.

## Run it as a hook

gate-cache works with [prek](https://github.com/j178/prek) and with [pre-commit](https://pre-commit.com) 3.2 or later. Each `gate-cache` hook takes the same arguments as the command line:

```yaml
repos:
  - repo: https://github.com/natelandau/gate-cache
    rev: v0.8.0
    hooks:
      - id: gate-cache
        name: pytest
        args: [--, uv, run, pytest]
        files: ^(src/|tests/)
      - id: gate-cache
        name: ruff
        args: [--, uv, run, ruff, check, .]
```

The hook runs at commit time and at push time. At commit time, gate-cache matches the content that you commit.

The hook runs in its own virtual environment, and the wrapped command inherits that environment. A command started with `uv run`, or a project command such as `just test`, runs in the project environment. `uv run` prints a warning that `VIRTUAL_ENV` does not match the project. The warning has no effect on the run.

The gate-cache that a hook installs records stats when recording is on, but that install has no dashboard UI. Only a release wheel contains the UI, and a hook builds gate-cache from source. A git or path dependency also builds from source and has no UI. To view the dashboard, run `gate-cache dashboard` from the install that `uv tool install gate-cache` makes.

Hooks, agents, and your terminal all read and write the same markers. When one of them runs `gate-cache -- uv run pytest` and it passes, the others skip `uv run pytest` on the same content.

## Examples

These examples show gate-cache inside the task runner of a project. When a recipe holds the wrapped command, everything that runs the recipe uses the same name and the same markers.

### justfile

```just
test:
    gate-cache -- uv run pytest

lint:
    gate-cache -- uv run ruff check .
```

After `just test` passes, the next `just test` on the same content skips pytest.

### Recipes with arguments

A recipe that passes its arguments to the command needs no `--name`. Each set of arguments gives a different command line, so each set has its own markers:

```just
test *args:
    gate-cache -- uv run pytest {{ args }}
```

`just test` runs under the name `uv run pytest`, and `just test -k unit` runs under the name `uv run pytest -k unit`. A pass of the unit tests never skips the full suite.

If the recipe gives `--name`, the arguments are not part of the name. Put them in the name, or a pass of `just test -k unit` also skips `just test`.

An absolute path in the command, such as `{{ justfile_directory() }}/tests`, puts the location of the worktree in the name. Each worktree then has its own markers, so a pass in one worktree never skips the gate in another. To share markers across worktrees, use relative paths.

### Inputs that git does not track

A marker does not cover ignored files, environment variables, or tool versions. To make a gate depend on one of these inputs, put its value in the name. When the value changes, the name changes, so no marker matches and the command runs again:

```just
# Run again when the uv version changes
test:
    gate-cache --name "test-uv$(uv --version | cut -d' ' -f2)" -- uv run pytest

# Run again when the ignored .env file changes
integration:
    gate-cache --name "integration-$(git hash-object .env)" -- uv run pytest tests/integration
```

`git hash-object` prints a hash of the file, so the name does not hold the secrets in `.env`. Do not put a secret value in a name, because the marker and `gate-cache status` record the name as plain text. Without `--name`, the command line is the name, so give `--name` to a command that takes a secret as an argument.

The shell of the recipe expands `$(...)` before gate-cache starts. A hook `entry` or `args` list does not go through a shell, so put the command in a recipe and call the recipe from the hook. To look up the gate with `gate-cache status --name`, give the expanded name, such as `test-uv0.13.0`.

### Makefile

```make
test:
	gate-cache -- uv run pytest

lint:
	gate-cache -- uv run ruff check .
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

### CI

gate-cache turns off caching when the `CI` variable is on. A variable is on when its value is not empty, `0`, or `false`. Case and spaces around the value do not matter. Many CI systems set `CI=true` in every job, for example GitHub Actions and GitLab CI/CD. Jenkins does not set `CI`.

When caching is off, gate-cache runs the command each time and writes no marker.

`GATE_CACHE_DISABLE` overrides `CI`. To keep caching on when `CI` is on, set `GATE_CACHE_DISABLE` to `0` or `false`:

```sh
GATE_CACHE_DISABLE=0 just test
```

To turn off caching when `CI` is not set, set `GATE_CACHE_DISABLE` to `1`:

```sh
GATE_CACHE_DISABLE=1 just test
```

## See what already passed

`gate-cache status` lists the names that passed on the current content, and the names that ran on it without a pass:

```console
$ gate-cache status
  tree:   aaff74984cccd156a469afa7d9ab10e4777beb24
  passed: uv run pytest
  missed: uv run ruff check . (exit code 1)
```

A name is missed when its command failed, or when it exited 0 but changed the files. A later pass of the same name removes it from the `missed` line.

With `--name`, it reports on one name. For a gate that ran without `--name`, give the same command after `--`. gate-cache then looks up the command line as the name:

```console
$ gate-cache status -- uv run ruff check .
  name:     uv run ruff check .
  tree:     aaff74984cccd156a469afa7d9ab10e4777beb24
  marker:   /path/to/repo/.git/gate-cache/7d94ca2f57ec0a77f60d328fb405d339fb0c2a645991b97c042ac54403104e9e
  result:   miss
  last run: exit code 1
```

The `last run` line shows only when the name ran on this content without a pass. The `duration` line shows how long the command ran when it passed.

For a scoped gate, give the same `--path` options with `--name` or the command. The report adds a `paths` line and a `scope` line, and the `tree` line shows the whole tree:

```console
$ gate-cache status --name api-test --path api/ --path uv.lock
  name:     api-test
  paths:    api/ uv.lock
  scope:    paths:7c462ce94adead1b7ab99f8e4212ffac194c562e0d178151207c1f01e0073615
  tree:     aaff74984cccd156a469afa7d9ab10e4777beb24
  marker:   /path/to/repo/.git/gate-cache/4156a896efe2ed16204b6d2525acbfbd9c4dd808dbfc135571e4f631b7d7754a
  result:   hit
  duration: 1m 34s
```

Without `--name` or a command, `status` also lists the scoped gates that passed or missed on the current content of their paths.

`status` runs nothing. With `--name` or a command, it exits 0 when a marker matches and 1 when none does. Without either, it exits 0 when at least one name passed. When gate-cache cannot match the content, for example during a merge conflict, the `tree` line gives the reason. For a scoped gate whose paths match no file, the `scope` line gives it.

With `--json`, `status` writes one JSON object to stdout instead of text. The exit codes do not change:

```console
$ gate-cache status --json
{
  "enabled": true,
  "tree": "aaff74984cccd156a469afa7d9ab10e4777beb24",
  "reason": null,
  "passed": ["uv run pytest"],
  "missed": [
    {"name": "uv run ruff check .", "exit_code": 1, "reason": "exit code 1", "timestamp": "2026-10-12T12:31:55Z"}
  ]
}
```

`reason` tells why gate-cache cannot match the content, and is `null` when it can. When caching is off, `enabled` is `false`, `reason` names the variable, and the other keys are empty or `null`. With `--name`, the object has the `name`, `marker`, `result`, `last_run`, and `duration` keys in place of `passed` and `missed`. `duration` is the run time in seconds of the matching pass, or `null`. With `--path`, `tree` holds the scope value, and the object adds the `paths` and `full_tree` keys.

## Start fresh

A marker records only the content of the files that git does not ignore. A new tool version, a changed environment variable, or a change to a service does not change that content, so the old markers still match. To make a gate run again when one of these inputs changes, put the input in the name, as [Inputs that git does not track](#inputs-that-git-does-not-track) shows.

`gate-cache clear` permanently deletes every marker for the repository, and the records of missed runs. After a clear, every gate runs again in full. Before it deletes anything, it shows a warning and asks you to type `yes`. Any other answer stops the command with exit code 1, and no markers are deleted:

```console
$ gate-cache clear
gate-cache: WARNING: this permanently deletes every recorded pass for this repository.
gate-cache:   markers: /path/to/repo/.git/gate-cache
gate-cache:   Every gate runs again in full, even on code that already passed.
gate-cache:   Recorded run stats are not affected.
gate-cache:   This cannot be undone.
gate-cache: type 'yes' to clear markers: yes
gate-cache: removed 3 markers
```

If standard input is not a terminal, as in a script, the command refuses with exit code 1 unless you give `--yes` (or `-y`):

```sh
gate-cache clear --yes
```

`GATE_CACHE_DISABLE=1` runs every command without the cache, for one command or for a whole session:

```sh
GATE_CACHE_DISABLE=1 git push
```

## Stats dashboard

gate-cache can record each run of a gate and show the record in a local dashboard. The dashboard shows how much time the skips saved, and how much remains after the time that gate-cache itself used. It also shows how often gates skip, how often a run waited for another run of the same gate, and which gates fail and pass on the same content. Recording is off until you turn it on:

```sh
gate-cache stats on
```

`gate-cache stats` without an action shows whether recording is on, what decided it, and where the config file and the data live:

```console
$ gate-cache stats
  recording:  on
  decided by: config
  config:     /path/to/config/gate-cache/config.toml
  data:       /path/to/state/gate-cache
```

The paths depend on your system, so run the command to see them. `gate-cache stats off` turns recording off. Both actions write `[stats] enabled` in the config file and keep every other line of the file. Recorded data stays in place when you turn recording off.

To open the dashboard, run:

```sh
gate-cache dashboard
```

The dashboard listens on `127.0.0.1` and opens in your browser. It listens on port 7878, or on a free port when 7878 is taken. With `--port N`, it listens on that port only, and the command fails when the port is in use. With `--no-browser`, it does not open a browser. Only one dashboard runs at a time. A second `gate-cache dashboard` prints the address of the running one and opens it, unless you give `--no-browser`. Press Ctrl-C to stop it.

The dashboard has pages for an overview, gates, recent activity, and flaky gates. The range picker at the top sets the time range. You can pick a relative range such as 7 days, a calendar period such as This week, or custom dates. The repo filter at the top accepts several repositories at once. On the overview, the Breakdown panel groups the runs by repo, gate, source (such as a git hook, CI, or a coding agent), branch, or machine. Click a repo to filter the dashboard to it, a gate to open its details, or any other row to see its runs. To scope the overview to some days, click a day on the calendar or the daily chart, or drag across days on the daily chart. Click the same day again or remove the chip to see the whole range again. A count on the overview, such as failures or an outcome, opens the Activity page with the runs that the count stands for. The dashboard updates while it runs, so new runs appear within seconds. The theme button at the top right cycles between the system theme (the default), light, and dark, and the dashboard remembers your choice.

`gate-cache stats clear` permanently deletes all recorded stats. You cannot undo it. Like `gate-cache clear`, it shows a warning and asks you to type `yes`. Any other answer stops the command with exit code 1, and no stats are deleted. While it waits for your answer, `gate-cache dashboard` cannot start, and it reports that a dashboard is already running or that stats clear is in progress. If standard input is not a terminal, as in a script, the command refuses with exit code 1 unless you give `--yes` (or `-y`):

```sh
gate-cache stats clear --yes
```

It keeps the random machine ID. It refuses while the dashboard runs. It does not delete markers. Use `gate-cache clear` for those.

### What gate-cache records

Each run of a gate adds one event with these fields:

- the time the run finished
- the path of the git directory of the repository
- the gate name and the `--path` values
- the tree key that the run used
- the outcome
- the run time of the command, and the time that a skip saved
- the exit code of the command
- the reason that caching was off, for a run without the cache
- the gate-cache version, the platform, and what started the run: CI, a git hook, a coding agent, or a terminal
- the path of the working tree, the directory in it where the gate ran, the branch, and the commit
- the URL of the `origin` remote, without user names or credentials
- the host name of the machine and a random machine ID
- the time that gate-cache took to decide, the age of the marker of a skip, and the CPU time and peak memory of the command
- the full command line, when `--name` gives a name that is not the command line
- the time the run waited for another run of the same gate, whether the wait reached its limit, and whether the run reported the failure of that run instead of running the command

An event holds no command output and no file content. The gate name is the command line unless you give `--name`, so a secret in a command line is in the record. When you give `--name`, the event also holds the command line, so a secret that you give to the command as an argument is in the record. Never put a secret in a gate name or in a command line. The working tree path and the host name often contain your user name or your real name. The machine ID is random and does not identify you. Recording is off until you turn it on. The data never leaves your machine, and `gate-cache stats clear` deletes it. The dashboard listens only on `127.0.0.1` and rejects requests for any other host name. Its pages load scripts, styles, and images only from the dashboard itself, and other sites cannot show the dashboard in a frame.

### When recording is on

The setting comes from the first of these that applies:

1. `GATE_CACHE_STATS`, when it is not empty. A value of `0` or `false` turns recording off, and any other value turns it on.
2. `CI`. When `CI` is on, recording is off.
3. `[stats] enabled` in the config file.
4. Off.

A CI runner is not your machine, so CI does not record unless `GATE_CACHE_STATS` is on. Recording never changes whether a command skips, its exit code, or its output. A failure to record is silent.

### Where the data lives

The data directory comes from the first of these that applies:

1. `GATE_CACHE_DATA_DIR`, when it is not empty. A relative path starts from the current directory.
2. `data_dir` in the `[stats]` table of the config file, when it is a text value that is not empty. A relative path starts from the directory of the config file, so every repository uses the same data.
3. The state directory of your platform.

A leading `~` in either value expands to your home directory. gate-cache ignores a `data_dir` value that is not text. `gate-cache stats` shows the data directory that applies.

```toml
[stats]
enabled = true
data_dir = "~/gate-cache-stats"
```

To try the dashboard on test data and keep your real stats unchanged, set a separate data directory:

```sh
GATE_CACHE_DATA_DIR=/tmp/gc-uat GATE_CACHE_STATS=1 gate-cache dashboard
```

## Settings

Five environment variables control gate-cache.

| Variable                  | Effect                                                                         | Default |
| ------------------------- | ------------------------------------------------------------------------------ | ------- |
| `GATE_CACHE_DISABLE`      | If on, turns off caching. If `0` or `false`, keeps caching on when `CI` is on. | not set |
| `CI`                      | If on, turns off caching. A value in `GATE_CACHE_DISABLE` overrides it.        | not set |
| `GATE_CACHE_MAX_AGE_DAYS` | Each time gate-cache records a result, it deletes markers older than this number of days. | `30`    |
| `GATE_CACHE_STATS`        | If on, records stats, even in CI. If `0` or `false`, turns recording off. If empty, `CI` and then the config file decide. | not set |
| `GATE_CACHE_DATA_DIR`     | The directory for recorded stats. If empty, `[stats] data_dir` in the config file and then the platform state directory decide. | not set |

A variable is on when its value is not empty, `0`, or `false`. Case and spaces around the value do not matter.

### Waiting for a concurrent run

The `[wait]` table of the config file, the file that `gate-cache stats` shows, sets two values. Each flag below goes before `--` and overrides its config value.

| Config key | Flag                             | Effect                                                                                                                                            | Default |
| ---------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| `timeout`  | `--wait-timeout SECONDS`         | The longest total wait of one run, in whole seconds. `0` turns waiting off.                                                                       | `900`   |
| `failed`   | `--on-wait-failure rerun\|report` | What a run does when the run that it waited for failed. `rerun` runs the command. `report` prints `NAME failed on tree HASH in WORKTREE (exit N), not running again` and exits with that code. | `rerun` |

```toml
[wait]
timeout = 300
failed = "report"
```

An invalid value in the config file prints a warning and uses the default. With `report`, only a command that exited with a code other than 0 counts as a failure. A run that passed but changed files, or a run that was interrupted, does not.

Each marker is one small file in the `.git` directory of the repository, so all worktrees of the repository share the markers. Waiting uses lock files in `.git/gate-cache-locks/`. gate-cache deletes old lock files with old markers, and `gate-cache clear` leaves them in place.

## Learn more

- [How gate-cache works](docs/how-it-works.md) describes the exact rules for a skip, what a marker covers, the marker format for tools that read markers directly, and how gate-cache stores and measures stats.
- `gate-cache --help` gives the full command reference.
- `gate-cache --skill` gives the guide for coding agents.
