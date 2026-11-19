---
name: gate-cache
description: "Use gate-cache, a CLI that skips a lint, type check, or test command when the same command already passed on the same file content. Use when a repository runs its checks through gate-cache, when a command prints 'already passed on tree' or 'already passed on paths', when you add, change, scope, or debug a gate-cache gate, or when the user asks which checks are flaky, slow, or cost the most time."
---

# gate-cache

gate-cache wraps a lint, type check, or test command. It runs the command and records a pass for the gate name and the content of every file that git does not ignore. When the same name runs again on the same content, gate-cache skips the command and exits 0. Uncommitted edits and untracked files are part of the content, so a pass on uncommitted work also skips when you commit that content.

The installed binary is the authority for syntax. Run `gate-cache --help` and `gate-cache SUBCOMMAND --help` for the options of this version. `gate-cache --version` prints the version that this guide matches.

## Read the output

When gate-cache runs a gate, it writes its own lines to stderr with the prefix `gate-cache:`. All other output comes from the wrapped command. The other commands print an error as a line that starts with `error:`, and a `hint:` line when there is a fix.

| Line | Meaning | Action |
| --- | --- | --- |
| `NAME already passed on tree HASH, skipping (saved 1m 34s)` | A pass for this name on this exact content exists. The command did not run, and gate-cache exits 0. | Treat the gate as passed. The result is valid. Do not run the tool directly to get the same answer again. |
| `NAME already passed on paths HASH, skipping` | The same, for a gate scoped with `--path`. Nothing under its paths changed. | Treat the gate as passed. |
| `NAME is running in WORKTREE (started 1m 12s ago), waiting` | Another run of this gate on this content is in progress. gate-cache waits for it, then skips if it passed, or runs the command. | Wait. The run is not a hang. Do not kill it or start the tool another way. |
| `NAME still running in WORKTREE after 15m 0s, running anyway` | The wait reached its limit, so the command runs without the lock. | Let it finish. Tell the user if it happens often. |
| `NAME failed on tree HASH in WORKTREE (exit N), not running again` | `--on-wait-failure report` is on, and the awaited run failed. gate-cache exits with code N and does not run the command. | Treat the gate as failed. Fix the cause, then run the same command again. |
| `files changed during the run, not recording pass` | The command exited 0 but changed files, so gate-cache wrote no marker. | If the command is a formatter or a fixer, wrap its check-only form. Otherwise, find which file the command writes. |
| `REASON, running without cache` | The command runs without the cache, and gate-cache writes no marker. REASON names the cause, such as `caching disabled in CI` or `--path docs/ matches no files`. | If a `--path` matches no files, correct the path. |
| `warning: could not record pass: ...` | The command passed, but gate-cache cannot write the marker. The exit code is unchanged. | Report the warning to the user. |

The saved time in parentheses is how long the command ran when it passed.

When the command runs, gate-cache exits with the exit code of the command. It exits 127 when the command is not found, 126 when it cannot run, and 128 plus N when signal N stops it. A usage error exits 2 and runs nothing.

A waiting run happens when two runs of the same gate and content overlap, for example two agents in two worktrees. The wait lasts at most 15 minutes by default. `--wait-timeout SECONDS` and `--on-wait-failure rerun|report` change the behavior, and the `wait_timeout` and `wait_on_failure` keys of the config file set them for every repository. The flags win over the config file. Waiting works on macOS and Linux only.

About one run in 50 of a gate that would skip runs the command anyway, as a spot check that the skip is still right. The `spot_check_one_run_in` key of the config file sets the rate for every repository, and `GATE_CACHE_SPOT_CHECK_ONE_RUN_IN` sets it for one shell. `0` turns spot checks off.

The config file sets values for every repository. To give one repository, or every repository that matches a pattern, its own values, put the keys in a `[projects."PATTERN"]` table at the end of the same file. A pattern that starts with `/` or `~` matches the folder of the repository. Any other pattern matches its remote, such as `github.com/owner/repo`. Never add a config file to the repository itself, because gate-cache reads only the user config file.

## Run checks in a repository that uses gate-cache

1. Run lint and tests with the commands that the repository documents in its agent instruction file, its README, or its contributing guide. The command can be a gate-cache command line, a package script, or a task-runner recipe. Do not assume that the repository uses any particular tool. Do not run the underlying tool directly. A direct run does not read or write the shared gate-cache markers.
2. If a gate skips, the check passed on this content. Continue with your task.
3. If a gate fails, fix the cause and run the same command again.

To see which gates passed on the current content, run `gate-cache status`. To look up one gate, run `gate-cache status --name NAME`, and add the same `--path` options that the gate uses. For a gate that ran without `--name`, give the same command after `--`, such as `gate-cache status -- npm run lint`. Add `--json` for machine-readable output.

To force a full run, set `GATE_CACHE_DISABLE=1` for one command, such as `GATE_CACHE_DISABLE=1 gate-cache --name test -- pytest`. Force a full run only for one of these reasons:

- The user asks for it.
- An input that gate-cache does not see changed, such as the installed version of a tool, an environment variable, or an ignored file.

## Find flaky and slow gates

gate-cache can record each run of a gate. The record shows which gates are flaky, which gates are slow, and how much time the gates cost. A flaky gate fails and passes on the same content.

If the user asks which checks are flaky, slow, or cost the most time, do these steps:

1. Run `gate-cache stats --json`. The `enabled` key shows whether recording is on.
2. If recording is off, tell the user that gate-cache can record the runs, and ask whether to turn recording on. Recording is a setting for the computer, but a `[projects]` table in the config file can turn it off for one repository. If the user agrees, run `gate-cache stats on`. The record starts with the next run of each gate.
3. If recording is on, run `gate-cache stats report --json`. The output has one row for each gate with its runs, skip rate, failures, run times, and the time it spent and saved.
4. To look at one gate, run `gate-cache stats report --name NAME --json`. The report groups `test@v22` under `test`, so give `--name test`. For a gate that ran without `--name`, give the command after `--`.

In the one-gate view, look for these signs:

- `flaky_trees` lists each tree on which the gate both failed and passed. Compare the `source` and `machine` of the failed runs and the passed runs. A failure from one source or one machine points to its environment.
- `exit_codes` with 137 means that a signal killed the command, often because the system ran out of memory.
- `uncached` shows why runs did not use the cache, such as files that changed during the run, or a reason that caching was off.
- `waits` shows runs that waited for another run of the same gate. Many waits or timeouts mean that agents run the gate at the same time.
- `slowdown` in the suite view shows a gate whose median run time grew since the window before. `trend` in the one-gate view shows the run time by day, week, or month, by the length of the window.
- For a gate that records its tests with `--junit`, `tests` names the slowest, flaky, and retried tests, and `failed_tests` on each failed run names the tests that failed.
- `spot_checks` lists the failed spot checks. A failed spot check means that a skip was not safe. The cause is a flaky test or an input that the gate's name and `--path` values do not cover. Fix the cause. Never run the gate again to get a skip.

To compare two periods, use `--since` and `--until`. The default window is the last 30 days. `--since` sets the length of the window, counted back from `--until`. For example, `--since 7d` covers the last week, and `--since 7d --until 7d` covers the week before it.

Inside a repository, the report covers that repository. Outside a repository, it covers every repository on the computer. `--repo NAME` or `--repo PATH` picks one repository, and `--all-repos` covers every repository. Outside a repository, `--name` needs `--repo`. In the one-gate view, `--limit N` sets the most items in each list. Each list shows `total` and `shown`, so you can tell when it is cut. Run `gate-cache stats report --help` for every option.

Every duration is in seconds. The [report format](https://natelandau.github.io/gate-cache/reference/report-format/) lists every key.

The dashboard is a page in a browser, for people. If the user wants to explore the record by hand, tell the user to run `gate-cache dashboard`. Only a copy of gate-cache installed from PyPI has the dashboard. A copy that the prek or pre-commit hook installs, or a copy from a git URL or a local path, has none. In that case, tell the user to run the dashboard from a copy installed from PyPI, such as with `pipx run gate-cache dashboard` or `uvx gate-cache dashboard`.

### Record the tests of a gate

With recording on, `--junit PATH` makes gate-cache read the JUnit XML report that the command writes, and record the name, outcome, and duration of each test. The dashboard then shows the slowest tests and the flaky tests by name. `--junit` never changes whether a gate skips, its output, or its exit code. With recording off, gate-cache ignores it.

gate-cache does not make the report. Tell the test tool to write it, to the same path:

```sh
gate-cache --name unit --junit reports/unit.xml -- pytest --junitxml=reports/unit.xml
gate-cache --name web --junit reports/web.xml -- npx vitest run --reporter=junit --outputFile=reports/web.xml
gate-cache --name go-test --junit reports/go.xml -- gotestsum --junitfile reports/go.xml
```

- Write the report to a path that git ignores, or outside the repository. A new file that git sees changes the content, and gate-cache then records no pass.
- Give each gate its own report path. If the name has an `@` key, put the key in the path too, such as `reports/test-node20.xml` for `test@node20`.
- A relative path is read from the directory where gate-cache starts.
- For a tool that writes one file for each test class, such as Maven Surefire or Gradle, give the folder. gate-cache reads the `.xml` files in it that the run wrote.
- Repeat `--junit` for each report file or folder.

## Write a gate

The syntax is `gate-cache [--name NAME] [--path PATHSPEC]... [--junit PATH]... -- COMMAND [ARGS...]`.

- `--` is required. Only `--name`, `--path`, `--junit`, `--wait-timeout`, `--on-wait-failure`, and `--spot-check` can come before it. Each takes a value as `--name VALUE` or `--name=VALUE`, except `--spot-check`, which takes none.
- Everything after `--` is the command, exactly as given. gate-cache does not use a shell. To use a pipe or `&&`, put the command in a script or use `sh -c '...'`.
- If the repository already runs the command from a script, a package script, or a task-runner recipe, put gate-cache there. Then the terminal, the git hooks, and agents all run the same gate and share its markers. Do not wrap the same command in two places. Do not add a task runner that the repository does not use.

### Choose the name

- Without `--name`, the name is the command line. Each command line then has its own markers, so a pass of `pytest -k unit` never skips `pytest`.
- With `--name`, the command after `--` is not part of the key. Give a short, stable name, such as `lint`, `typecheck`, or `test`, to a gate whose command line is fixed.
- A gate in a script, a package script, a task-runner recipe, or a hook must have a `--name` when its command line is fixed. Without one, `gate-cache status` and the stats dashboard show the full command line as the gate name. Any change to the command line then also starts a new gate with no history. A recipe that passes its own arguments on to the command is the exception, as the next item explains.
- Keep a name free of spaces, so that it reads as a name and the `@` rule in "Inputs that git does not see" applies to it.
- With `--name`, the command after `--` does not count. `gate-cache --name tests -- pytest -k unit` and `gate-cache --name tests -- pytest -k integration` are the same gate, so after the first one passes, the second one skips. If a recipe passes its own arguments on to the command, such as a test filter, do not give it a fixed `--name`. Give no `--name`, or run the command without gate-cache when the recipe gets arguments.
- The working directory is not part of the key. If the same command reads different files in different directories, give each directory its own name.

### Inputs that git does not see

A marker covers only the name and the content of the files that git does not ignore. A marker does not cover anything outside those files: ignored files, the environment variables of the shell, the versions of the tools installed on the computer, or external services. If a gate depends on one of these inputs, put the value in the name, after an `@`. A changed value gives a new name, so the command runs again:

```sh
gate-cache --name "test@node$(node --version)" -- npm test
gate-cache --name "integration@$(git hash-object .env)" -- pytest tests/integration
```

The text before the first `@` is the gate, and the text after it is the key. The stats dashboard counts the runs of every key toward the gate, so `test@nodev20.11.0` and `test@nodev22.1.0` show as one gate, `test`. The rule applies only to a name with no spaces and with text on both sides of the `@`. To key on more than one input, join the values after one `@`, or hash them together into one value. Do not use any other separator, such as `-`, for a key. With another separator, each value shows as its own gate.

`git hash-object` prints a hash of the file, so the name does not hold the content of `.env`.

Never put a secret in a name. Markers and `gate-cache status` store the name as plain text. Without `--name`, the command line is the name, so give `--name` to a command whose command line holds a secret.

Never wrap a check that depends on the commit message, the branch name, or anything on a remote.

### What to wrap

Wrap a command whose result depends only on its name and the files that git sees. Lint, format check, type check, spell check, and test commands are good gates.

Do not wrap these commands:

- A command that writes files, such as a formatter or a linter with a fix option. gate-cache never writes a marker for it. Wrap the form that only checks, such as `prettier --check .` in place of `prettier --write .`.
- A command whose output a later step needs, such as a build. A skip produces no output.
- A deploy, a release, or any command with effects outside the repository.

## Scope a gate with --path

A gate with `--path` options matches only the content under those paths. A change elsewhere in the repository does not make the gate run again. The same is true for a rebase that brings in only such changes. If the repository has several parts and a gate reads only some of them, use `--path`.

```sh
gate-cache --name api-test --path api/ --path requirements.txt -- pytest api/tests
```

The pathspec rules:

- Each `--path` is a git pathspec, read from the top of the repository. The working directory has no effect, so a script that runs in `api/` also writes `--path api/`.
- Repeat `--path` once for each path. The order has no effect. A directory covers every file under it.
- `*` also matches `/`, so `'*.toml'` matches a `.toml` file in every directory.
- `'**/package.json'` matches only a `package.json` inside a directory. To also match the top-level one, use `':(glob)**/package.json'`.
- `':(exclude)PATH'` removes files from the scope, as in `--path scripts/ --path ':(exclude)scripts/fixtures/'`.
- Quote each pathspec that holds `*`, `:(`, or `!`, so the shell passes it unchanged.
- If a path matches no file, gate-cache runs the command without the cache and prints the path. A typo therefore never makes a gate skip.

The gate skips when nothing under its paths changed. A path that is missing from the list makes the gate skip when it must run, and that hides a real failure. List everything the command reads that git tracks:

- The source and test directories that it checks.
- Lock files and dependency manifests, such as `requirements.txt`, `uv.lock`, `package.json`, `pnpm-lock.yaml`, `Cargo.lock`, or `go.sum`.
- Tool config, such as `pyproject.toml`, `tsconfig*.json`, `.eslintrc*`, or `vitest.config.*`.
- Shared fixtures, schemas, or generated contracts from other parts of the repository.
- The script, package file, or task-runner file that defines the gate.

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
        name: test
        args: [--name, test, --, npm, test]
```

- Hook `args` do not go through a shell. A name that uses `$(...)` must live in a script or a task-runner recipe that the hook calls.
- At commit time, gate-cache matches the staged content that you commit.
- The hook starts the command with the `PATH` of the developer, so a bare tool name finds the same copy as in the terminal. If the tool is installed only in the project, such as in `.venv/bin` or `node_modules/.bin`, start the command with the runner that the project already uses, such as `npm test`, `bundle exec`, or `uv run`, or with a path such as `.venv/bin/pytest`.
- If the project already runs its checks from a script, a package script, or a task-runner recipe, a local hook that calls that command is simpler. A commit, a push, an agent, and the terminal then all run the same command:

```yaml
repos:
  - repo: local
    hooks:
      - id: test
        name: test
        entry: npm test
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

- Never run `gate-cache clear` or `gate-cache stats clear` unless the user asks. Both permanently delete data. Give `--yes` only when the user asked for the deletion. To show the user what a clear deletes, run it with `--dry-run` first. After a tool upgrade that affects one gate, clear only that gate with `gate-cache clear --name NAME`.
- `gate-cache stats clear --all-repos` deletes the stats of every repository, and only a person at a terminal can confirm it. If the user wants it, ask them to run it themselves.
- Never edit or delete files in `{{marker_dir}}`.
- Never turn stats recording on or off unless the user asks.
- To try stats or the dashboard on test data, set `GATE_CACHE_DATA_DIR` to a temporary directory and `GATE_CACHE_STATS=1` for that command, so it never writes to the user's real stats.
- Never set `GATE_CACHE_DISABLE=1` in a script, a recipe, a hook, a shell profile, or a committed file. It removes every skip.
- Never put a secret in a gate name or in the command line of a gate without `--name`.
- A line that ends with `waiting` is normal. Never kill the run, and never run the tool directly to avoid the wait.
- A wait can last as long as the wait timeout, 15 minutes by default. If your tool stops a command sooner, run the gate in the background or increase the time limit of the tool. You can also give a smaller `--wait-timeout`.
- Never edit or delete files in `.git/gate-cache-locks/`. Never change the `wait_timeout` or `wait_on_failure` settings or add `--wait-timeout 0` unless the user asks.
- When a gate skips, do not run the tool another way to confirm the result.
