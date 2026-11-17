---
name: gate-cache
description: "Use gate-cache, a CLI that skips a lint, type check, or test command when the same command already passed on the same file content. Use when a repository runs its checks through gate-cache, when a command prints 'already passed on tree' or 'already passed on paths', or when you add, change, scope, or debug a gate-cache gate."
---

# gate-cache

gate-cache wraps a lint, type check, or test command. It runs the command and records a pass for the gate name and the content of every file that git does not ignore. When the same name runs again on the same content, gate-cache skips the command and exits 0. Uncommitted edits and untracked files are part of the content, so a pass on uncommitted work also skips when you commit that content.

The installed binary is the authority for syntax. Run `gate-cache --help` and `gate-cache SUBCOMMAND --help` for the options of this version. `gate-cache --version` prints the version that this guide matches.

## Read the output

gate-cache writes its own lines to stderr with the prefix `gate-cache:`. All other output comes from the wrapped command.

| Line | Meaning | Action |
| --- | --- | --- |
| `NAME already passed on tree HASH, skipping (saved 1m 34s)` | A pass for this name on this exact content exists. The command did not run, and gate-cache exits 0. | Treat the gate as passed. The result is valid. Do not run the tool directly to get the same answer again. |
| `NAME already passed on paths HASH, skipping` | The same, for a gate scoped with `--path`. Nothing under its paths changed. | Treat the gate as passed. |
| `NAME is running in WORKTREE (started 1m 12s ago), waiting` | Another run of this gate on this content is in progress. gate-cache waits for it, then skips if it passed, or runs the command. | Wait. The run is not a hang. Do not kill it or start the tool another way. |
| `NAME still running in WORKTREE after 15m 0s, running anyway` | The wait reached its limit, so the command runs without the lock. | Let it finish. Tell the user if it happens often. |
| `NAME failed on tree HASH in WORKTREE (exit N), not running again` | `--on-wait-failure report` is on, and the awaited run failed. gate-cache exits with code N and does not run the command. | Treat the gate as failed. Fix the cause, then run the recipe again. |
| `files changed during the run, not recording pass` | The command exited 0 but changed files, so gate-cache wrote no marker. | If the command is a formatter or a fixer, wrap its check-only form. Otherwise, find which file the command writes. |
| `REASON, running without cache` | The command runs without the cache, and gate-cache writes no marker. REASON names the cause, such as `caching disabled in CI` or `--path docs/ matches no files`. | If a `--path` matches no files, correct the path. |
| `warning: could not record pass: ...` | The command passed, but gate-cache cannot write the marker. The exit code is unchanged. | Report the warning to the user. |

The saved time in parentheses is how long the command ran when it passed.

When the command runs, gate-cache exits with the exit code of the command. It exits 127 when the command is not found, 126 when it cannot run, and 128 plus N when signal N stops it. A usage error exits 2 and runs nothing.

A waiting run happens when two runs of the same gate and content overlap, for example two agents in two worktrees. The wait lasts at most 15 minutes by default. `--wait-timeout SECONDS` and `--on-wait-failure rerun|report` change the behavior, and the `[wait]` table of the config file sets them for every run. The flags win over the config file. Waiting works on macOS and Linux only.

## Run checks in a repository that uses gate-cache

1. Run lint and tests the way the repository documents them, usually a task-runner recipe such as `just test`, `make lint`, or `npm run check`. Do not run the underlying tool directly. A direct run does not read or write the shared gate-cache markers.
2. If a gate skips, the check passed on this content. Continue with your task.
3. If a gate fails, fix the cause and run the same recipe again.

To see which gates passed on the current content, run `gate-cache status`. To look up one gate, run `gate-cache status --name NAME`, and add the same `--path` options that the gate uses. For a gate that ran without `--name`, give the same command after `--`, such as `gate-cache status -- uv run ruff check .`. Add `--json` for machine-readable output.

To force a full run, set `GATE_CACHE_DISABLE=1` for one command, such as `GATE_CACHE_DISABLE=1 just test`. Force a full run only for one of these reasons:

- The user asks for it.
- An input that gate-cache does not see changed, such as a tool version, an environment variable, or an ignored file.

## Write a gate

The syntax is `gate-cache [--name NAME] [--path PATHSPEC]... -- COMMAND [ARGS...]`.

- `--` is required. Only `--name` and `--path` can come before it, each as `--name VALUE` or `--name=VALUE`.
- Everything after `--` is the command, exactly as given. gate-cache does not use a shell. To use a pipe or `&&`, put the command in a script or use `sh -c '...'`.
- Put gate-cache in the task-runner recipe that holds the command. Then the terminal, the git hooks, and agents all run the same gate and share its markers. Do not wrap the same command in two places.

### Choose the name

- Without `--name`, the name is the command line. Each set of arguments then has its own markers, so a pass of `pytest -k unit` never skips `pytest`.
- With `--name`, the arguments are not part of the key. Give a short, stable name, such as `lint`, `typecheck`, or `test`, to a gate whose command line is fixed.
- If a recipe passes extra arguments to its command, such as a test filter, do not give it a fixed `--name`. With a fixed name, a pass with a filter also skips the full suite. When the recipe gets arguments, run the command without gate-cache. Another option is to give no `--name`.
- The working directory is not part of the key. If the same command reads different files in different directories, give each directory its own name.

### Inputs that git does not see

A marker covers only the name and the files that git does not ignore. It does not cover ignored files such as `.env`, environment variables, tool versions that no lock file pins, or external services. If a gate depends on one of these inputs, put the value in the name. A changed value gives a new name, so the command runs again:

```sh
gate-cache --name "test-node$(node --version)" -- npm test
gate-cache --name "integration-$(git hash-object .env)" -- uv run pytest tests/integration
```

`git hash-object` prints a hash of the file, so the name does not hold the content of `.env`.

Never put a secret in a name. Markers and `gate-cache status` store the name as plain text. Without `--name`, the command line is the name, so give `--name` to a command that takes a secret as an argument.

Never wrap a check that depends on the commit message, the branch name, or anything on a remote.

### What to wrap

Wrap a command whose result depends only on its name and the files that git sees. Lint, format check, type check, spell check, and test commands are good gates.

Do not wrap these commands:

- A command that writes files, such as a formatter or a linter with a fix option. gate-cache never writes a marker for it. Wrap its check-only form, such as `ruff format --check` or `prettier --check`.
- A command whose output a later step needs, such as a build. A skip produces no output.
- A deploy, a release, or any command with effects outside the repository.

## Scope a gate with --path

A gate with `--path` options matches only the content under those paths. A change elsewhere in the repository does not make the gate run again. The same is true for a rebase that brings in only such changes. If the repository has several parts and a gate reads only some of them, use `--path`.

```sh
gate-cache --name api-test --path api/ --path uv.lock -- uv run pytest api/tests
```

The pathspec rules:

- Each `--path` is a git pathspec, read from the top of the repository. The working directory has no effect, so a recipe that runs in `api/` also writes `--path api/`.
- Repeat `--path` once for each path. The order has no effect. A directory covers every file under it.
- `*` also matches `/`, so `'*.toml'` matches a `.toml` file in every directory.
- `'**/justfile'` matches only a `justfile` inside a directory. To also match the top-level one, use `':(glob)**/justfile'`.
- `':(exclude)PATH'` removes files from the scope, as in `--path scripts/ --path ':(exclude)scripts/fixtures/'`.
- Quote each pathspec that holds `*`, `:(`, or `!`, so the shell passes it unchanged.
- If a path matches no file, gate-cache runs the command without the cache and prints the path. A typo therefore never makes a gate skip.

The gate skips when nothing under its paths changed. A path that is missing from the list makes the gate skip when it must run, and that hides a real failure. List everything the command reads that git tracks:

- The source and test directories that it checks.
- Lock files and dependency manifests, such as `uv.lock`, `package.json`, `pnpm-lock.yaml`, `Cargo.lock`, or `go.sum`.
- Tool config, such as `pyproject.toml`, `tsconfig*.json`, `.eslintrc*`, or `vitest.config.*`.
- Shared fixtures, schemas, or generated contracts from other parts of the repository.
- The task-runner file or script that defines the gate.

If you are not sure that the command reads a file, include it. An extra path costs a run that was not necessary. A missing path hides a failure.

If a command reads the whole repository, do not scope its gate. Examples are a spell check of every file and a hook runner with `--all-files`.

When a change makes a scoped gate read a new file or directory outside its paths, add the path in the same change. When you move or rename a path, update every list that names it.

## Git hooks

gate-cache works with prek and with pre-commit 3.2 or later. The hook id is `gate-cache`, and its `args` are the same as the command line:

```yaml
repos:
  - repo: https://github.com/natelandau/gate-cache
    rev: v{{version}}
    hooks:
      - id: gate-cache
        name: pytest
        args: [--name, pytest, --, uv, run, pytest]
```

- Hook `args` do not go through a shell. A name that uses `$(...)` must live in a task-runner recipe that the hook calls.
- At commit time, gate-cache matches the staged content that you commit.
- The hook runs in its own virtual environment, which comes first on `PATH`. Start the command with `uv run`, an absolute path, or a project task such as `just test`, not a bare tool name.
- If the project already wraps its checks in task-runner recipes, a local hook that calls the recipe is simpler. It runs the recipe from the `PATH` of the developer:

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

## Where markers live

Markers are files in the git common directory, `{{marker_dir}}`. All worktrees of a repository share them, and so do hooks, agents, and terminals. A fresh clone has no markers. A marker expires after `GATE_CACHE_MAX_AGE_DAYS` days (default {{max_age_days}}).

When `CI` is on, gate-cache turns off caching. A variable is on when its value is not empty, `0`, or `false`. `GATE_CACHE_DISABLE=0` keeps caching on in CI. Do not change CI jobs to add or remove gate-cache.

The command also runs without the cache when the content is unknown. Examples are a merge conflict, sparse checkout, and a submodule that is not checked out or has local changes. The printed reason names the cause.

## Make sure that a gate works

After you add or change a gate, do these steps to make sure that it works:

1. Run the gate. Make sure that it passes, and that gate-cache does not print `files changed during the run` or `matches no files`.
2. Run the gate again. Make sure that it prints `already passed on`.
3. For a scoped gate, change a line in a file outside its paths and run it. Make sure that it skips. Then change a file inside its paths and run it. Make sure that it runs. Revert both changes.
4. Run `gate-cache status`. Make sure that it lists the gate as passed.

## Rules

- Never run `gate-cache clear` or `gate-cache stats clear` unless the user asks. Both permanently delete data. Give `--yes` only when the user asked for the deletion.
- Never edit or delete files in `{{marker_dir}}`.
- Never turn stats recording on or off unless the user asks.
- To try stats or the dashboard on test data, set `GATE_CACHE_DATA_DIR` to a temporary directory and `GATE_CACHE_STATS=1` for that command, so it never writes to the user's real stats.
- Never set `GATE_CACHE_DISABLE=1` in a recipe, a hook, a shell profile, or a committed file. It removes every skip.
- Never put a secret in a gate name or in the command line of a gate without `--name`.
- A line that ends with `waiting` is normal. Never kill the run, and never run the tool directly to avoid the wait.
- A wait can last as long as the wait timeout, 15 minutes by default. If your tool stops a command sooner, run the gate in the background or increase the time limit of the tool. You can also give a smaller `--wait-timeout`.
- Never edit or delete files in `.git/gate-cache-locks/`. Never change `[wait]` settings or add `--wait-timeout 0` unless the user asks.
- When a gate skips, do not run the tool another way to confirm the result.
