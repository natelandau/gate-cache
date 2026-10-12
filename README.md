# gate-cache

Skip a command that already passed on the same code.

A lint or test command often runs many times on code that did not change. It runs when you finish the work, in a pre-commit hook, after a rebase that changed nothing, and in a pre-push hook. When an agent works in the repository, it runs the same command again. If the command takes minutes, the repeat runs take most of the time between finished code and a pushed branch.

gate-cache remembers which commands passed on which code. It wraps a command, and the command line is the name of the gate. When the command passes, gate-cache writes a marker for that name and for the exact content of the files in the working copy that git does not ignore. The next time the same name runs on the same content, gate-cache finds the marker, skips the command, and exits 0 at once.

```console
$ gate-cache -- uv run pytest
============================= 412 passed in 94.20s =============================

$ gate-cache -- uv run pytest
gate-cache: uv run pytest already passed on tree aaff74984ccc, skipping
```

A change to any file that git does not ignore changes the content, so no marker matches and the command runs again. A CI runner that starts from a fresh clone has no markers, so it runs every command.

## Install

gate-cache requires Python 3.11 or later, on macOS or Linux.

```sh
uv tool install gate-cache
```

The prek and pre-commit hooks install gate-cache themselves, so the hooks work without this step.

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

## Run it as a hook

gate-cache works with [prek](https://github.com/j178/prek) and with [pre-commit](https://pre-commit.com) 3.2 or later. Each `gate-cache` hook takes the same arguments as the command line:

```yaml
repos:
  - repo: https://github.com/natelandau/gate-cache
    rev: v0.1.0
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

With `--name`, it reports on one name. For a gate that ran without `--name`, give the command line as the name:

```console
$ gate-cache status --name "uv run ruff check ."
  name:     uv run ruff check .
  tree:     aaff74984cccd156a469afa7d9ab10e4777beb24
  marker:   /path/to/repo/.git/gate-cache/7d94ca2f57ec0a77f60d328fb405d339fb0c2a645991b97c042ac54403104e9e
  result:   miss
  last run: exit code 1
```

The `last run` line shows only when the name ran on this content without a pass.

`status` runs nothing. With `--name`, it exits 0 when a marker matches and 1 when none does. Without `--name`, it exits 0 when at least one name passed. When gate-cache cannot match the content, for example during a merge conflict, the `tree` line gives the reason.

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

`reason` tells why gate-cache cannot match the content, and is `null` when it can. When caching is off, `enabled` is `false`, `reason` names the variable, and the other keys are empty or `null`. With `--name`, the object has the `name`, `marker`, `result`, and `last_run` keys in place of `passed` and `missed`.

## Start fresh

A marker records only the content of the files that git does not ignore. A new tool version, a changed environment variable, or a change to a service does not change that content, so the old markers still match. To make a gate run again when one of these inputs changes, put the input in the name, as [Inputs that git does not track](#inputs-that-git-does-not-track) shows.

`gate-cache clear` deletes every marker for the repository, and the records of missed runs:

```console
$ gate-cache clear
gate-cache: removed 3 markers
```

`GATE_CACHE_DISABLE=1` runs every command without the cache, for one command or for a whole session:

```sh
GATE_CACHE_DISABLE=1 git push
```

## Settings

Three environment variables control gate-cache.

| Variable                  | Effect                                                                         | Default |
| ------------------------- | ------------------------------------------------------------------------------ | ------- |
| `GATE_CACHE_DISABLE`      | If on, turns off caching. If `0` or `false`, keeps caching on when `CI` is on. | not set |
| `CI`                      | If on, turns off caching. A value in `GATE_CACHE_DISABLE` overrides it.        | not set |
| `GATE_CACHE_MAX_AGE_DAYS` | gate-cache deletes markers older than this number of days.                     | `30`    |

A variable is on when its value is not empty, `0`, or `false`. Case and spaces around the value do not matter.

Each marker is one small file in the `.git` directory of the repository, so all worktrees of the repository share the markers.

## Learn more

- [How gate-cache works](docs/how-it-works.md) describes the exact rules for a skip, what a marker covers, and the marker format for tools that read markers directly.
- `gate-cache --help` gives the full command reference.
