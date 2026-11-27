---
name: gate-cache
description: "Use when a repository runs its lint, type check, or test commands through gate-cache; when a command prints 'already passed on tree' or 'already passed on paths'; when adding, changing, scoping, or debugging a gate-cache gate; or when the user asks which checks are flaky, slow, or cost the most time."
---

# gate-cache

gate-cache wraps a lint, type check, or test command. On a pass it records a marker for the gate name plus the content of every file git does not ignore, uncommitted and untracked files included. Same name on same content again: skips the command, exits 0. A pass on uncommitted work also skips once that content is committed.

Syntax authority: the installed binary. `gate-cache --help`, `gate-cache SUBCOMMAND --help`. `gate-cache --version` prints the version this guide matches.

## Read the output

gate-cache writes its own lines to stderr, prefixed `gate-cache:`. All other output is the wrapped command's. Other subcommands print errors as `error:` lines, plus a `hint:` line when a fix exists.

| Line | Meaning | Action |
| --- | --- | --- |
| `NAME already passed on tree HASH, skipping (saved 1m 34s)` | Pass exists for this name and content. Command not run, exit 0. Saved time = the passing run's duration. | Gate passed. Do not rerun the tool another way to confirm. |
| `NAME already passed on paths HASH, skipping` | Same, for a gate scoped with `--path`: nothing under its paths changed. | Gate passed. |
| `NAME is running in WORKTREE (started 1m 12s ago), waiting` | Another run of this gate on this content is in progress. gate-cache waits, then skips if it passed, else runs. | Wait. Not a hang. Do not kill it or run the tool another way. |
| `NAME still running in WORKTREE after 15m 0s, running anyway` | Wait limit reached; command runs without the lock. | Let it finish. Tell the user if frequent. |
| `NAME failed on tree HASH in WORKTREE (exit N), not running again` | `--on-wait-failure report` is set and the awaited run failed. Exits N without running. | Gate failed. Fix the cause, rerun the same command. |
| `files changed during the run, not recording pass` | Command exited 0 but changed files, so no marker. | Formatter or fixer: wrap its check-only form. Otherwise find the file the command writes. |
| `REASON, running without cache` | Runs uncached, no marker. REASON names the cause, e.g. `caching disabled in CI`, `--path docs/ matches no files`. | Path matches no files: fix the path. |
| `warning: could not record pass: ...` | Command passed, marker write failed. Exit code unchanged. | Report to the user. |

Exit codes: the command's own when it runs. 127 command not found, 126 cannot run, 128+N killed by signal N, 2 usage error (nothing runs).

## Settings

Config file: user-level only; `gate-cache stats` prints its path on the `config` line. Never add a config file to the repository; gate-cache does not read one there.

- Per-repo overrides: `[projects."PATTERN"]` table at the end of the file. Pattern starting `/` or `~` matches the repository folder; any other pattern matches the remote, e.g. `github.com/owner/repo`.
- Waiting: when two runs of the same gate and content overlap (e.g. agents in two worktrees), the second waits, at most 15 minutes by default. Flags `--wait-timeout SECONDS`, `--on-wait-failure rerun|report`; config keys `wait_timeout`, `wait_on_failure`. Flags win. macOS and Linux only.
- Spot checks: about 1 run in 50 that would skip runs anyway, to check the skip is still right. Config key `spot_check_one_run_in`, env `GATE_CACHE_SPOT_CHECK_ONE_RUN_IN`; `0` disables.
- CI: caching is off when `CI` is set to anything but empty, `0`, or `false`. `GATE_CACHE_DISABLE=0` keeps it on. Do not edit CI jobs to add or remove gate-cache.
- Markers: files in the git common directory, `{{marker_dir}}`, shared by all worktrees, hooks, agents, and terminals. Fresh clone has none. Expire after `GATE_CACHE_MAX_AGE_DAYS` days (default {{max_age_days}}).
- Content unknown (merge conflict, sparse checkout, submodule not checked out or with local changes): runs uncached; the printed reason names the cause.

## Run checks in a repository that uses gate-cache

1. Run lint and tests with the commands the repository documents (agent instruction file, README, contributing guide): a gate-cache command line, package script, or task-runner recipe. Never run the underlying tool directly; a direct run neither reads nor writes the shared markers.
2. Gate skips: the check passed on this content. Continue.
3. Gate fails: fix the cause, rerun the same command.

Status: `gate-cache status` lists gates passed on the current content. One gate: `gate-cache status --name NAME` plus the gate's `--path` options. Gate without `--name`: give its command after `--`, e.g. `gate-cache status -- npm run lint`. `--json` for machine-readable output.

Force a full run with `GATE_CACHE_DISABLE=1` on one command, e.g. `GATE_CACHE_DISABLE=1 gate-cache --name test -- pytest`, only when:

- the user asks, or
- an input gate-cache does not see changed: installed tool version, environment variable, ignored file.

## Find flaky and slow gates

gate-cache can record each run. Flaky = fails and passes on the same content.

When the user asks which checks are flaky, slow, or cost the most time:

1. `gate-cache stats --json`. Key `enabled` shows whether recording is on.
2. Off: tell the user gate-cache can record runs and ask whether to turn it on. Yes: `gate-cache stats on`. Recording is per computer; a `[projects]` table can turn it off for one repository. Data starts with each gate's next run.
3. On: `gate-cache stats report --json`. One row per gate: runs, skip rate, failures, run times, time spent and saved.
4. One gate: `gate-cache stats report --name NAME --json`. Keyed names group under the base: `test@v22` is `--name test`. Gate without `--name`: command after `--`.

Signs in the one-gate view:

- `flaky_trees`: trees where the gate both failed and passed. Compare `source` and `machine` of failed vs passed runs; failures from one source or machine point to its environment.
- `exit_codes` containing 137: killed by signal, often out of memory.
- `uncached`: why runs skipped the cache (files changed during run, caching off).
- `waits`: runs that waited on another run. Many waits or timeouts = agents running the gate concurrently.
- `slowdown` (suite view): median run time grew versus the previous window. `trend`: run time by day, week, or month, by window length.
- `tests` (gates with `--junit`): slowest, flaky, and retried tests. `failed_tests` on each failed run: tests that failed.
- `spot_checks`: failed spot checks. Each means a skip was unsafe, caused by a flaky test or an input the name and `--path` values miss. Fix the cause. Never rerun to get a skip.

Options:

- Window: default last 30 days. `--since` = window length back from `--until`. `--since 7d` = last week; `--since 7d --until 7d` = the week before.
- Scope: inside a repository, that repository; outside, all repositories. `--repo NAME|PATH` picks one, `--all-repos` covers all. Outside a repository, `--name` needs `--repo`.
- `--limit N` caps each list in the one-gate view; each list reports `total` and `shown`.
- Durations are seconds. Every key: [report format](https://natelandau.github.io/gate-cache/reference/report-format/). All options: `gate-cache stats report --help`.

Dashboard: a browser page for people. User wants to explore by hand: tell them to run `gate-cache dashboard`. Only PyPI installs include it; copies installed by the prek or pre-commit hook, a git URL, or a local path do not. Then suggest `pipx run gate-cache dashboard` or `uvx gate-cache dashboard`.

### Record the tests of a gate

With recording on, `--junit PATH` reads the JUnit XML report the command writes and records each test's name, outcome, and duration, so the dashboard shows slowest and flaky tests by name. Never changes skipping, output, or exit code. Ignored when recording is off.

gate-cache does not create the report. Point the test tool at the same path:

```sh
gate-cache --name unit --junit reports/unit.xml -- pytest --junitxml=reports/unit.xml
gate-cache --name web --junit reports/web.xml -- npx vitest run --reporter=junit --outputFile=reports/web.xml
gate-cache --name go-test --junit reports/go.xml -- gotestsum --junitfile reports/go.xml
```

- Report path must be git-ignored or outside the repository. A new file git sees changes the content, so no pass is recorded.
- One report path per gate. Keyed name: key in the path too, e.g. `reports/test-node20.xml` for `test@node20`.
- Relative paths resolve from the directory gate-cache starts in.
- One file per test class (Maven Surefire, Gradle): give the folder; gate-cache reads the `.xml` files the run wrote.
- Repeat `--junit` per file or folder.

## Write a gate

Syntax: `gate-cache [--name NAME] [--path PATHSPEC]... [--junit PATH]... -- COMMAND [ARGS...]`

- `--` required. Before it, only `--name`, `--path`, `--junit`, `--wait-timeout`, `--on-wait-failure`, `--spot-check`. Values as `--name VALUE` or `--name=VALUE`; `--spot-check` takes none.
- After `--`: the command, run exactly as given, no shell. For pipes or `&&`, use a script or `sh -c '...'`.
- Repository already runs the command from a script, package script, or task-runner recipe: put gate-cache there, so terminal, hooks, and agents share one gate and its markers. Never wrap the same command in two places. Never add a task runner the repository does not use.

### Choose the name

- No `--name`: the command line is the name. `pytest -k unit` passing never skips `pytest`.
- With `--name`: the command after `--` is not part of the key. `gate-cache --name tests -- pytest -k unit` and `gate-cache --name tests -- pytest -k integration` are one gate; the second skips after the first passes.
- Fixed command line in a script, recipe, or hook: give a short stable `--name` (`lint`, `typecheck`, `test`). Without one, `gate-cache status` and the dashboard show the full command line, and any edit to it starts a new gate with no history.
- Recipe that forwards its own arguments (e.g. a test filter) to the command: no fixed `--name`. Give no `--name`, or skip gate-cache when the recipe gets arguments.
- No spaces in names, so the `@` key rule below applies.
- Working directory is not part of the key. Same command reading different files in different directories: one name per directory.

### Inputs that git does not see

A marker covers only the name and git-visible file content. Not covered: ignored files, environment variables, installed tool versions, external services. Gate depends on one: put its value in the name after `@`. Changed value = new name = command reruns.

```sh
gate-cache --name "test@node$(node --version)" -- npm test
gate-cache --name "integration@$(git hash-object .env)" -- pytest tests/integration
```

- Text before the first `@` is the gate; after it, the key. Stats group all keys under the gate: `test@nodev20.11.0` and `test@nodev22.1.0` show as `test`. Applies only to names with no spaces and text on both sides of `@`.
- Several inputs: join them after one `@`, or hash them into one value. Never another separator such as `-`; each value would show as its own gate.
- `git hash-object` keeps file content out of the name.
- Never put a secret in a name: markers and `gate-cache status` store names as plain text. Command line holds a secret: give `--name`.
- Never wrap a check that depends on the commit message, branch name, or anything on a remote.

### What to wrap

Wrap commands whose result depends only on the name and git-visible files: lint, format check, type check, spell check, tests.

Commands that finish in about a second (many linters, format checks, type checkers): leave unwrapped by default. A skip saves almost nothing, and an input git does not see can still make the gate skip wrongly. Wrap one when the user asks. A fast command already wrapped is not a defect.

Never wrap:

- Commands that write files (formatters, linters with a fix option). No marker is ever written. Wrap the check-only form: `prettier --check .`, not `prettier --write .`.
- Commands whose output a later step needs, such as a build. A skip produces no output.
- Deploys, releases, anything with effects outside the repository.

## Scope a gate with --path

With `--path`, a gate matches only content under those paths; changes elsewhere, including a rebase that brings only such changes, do not rerun it. Use it when a multi-part repository has a gate that reads only some parts.

```sh
gate-cache --name api-test --path api/ --path requirements.txt -- pytest api/tests
```

Pathspec rules:

- Git pathspec, from the repository root regardless of working directory. A script running in `api/` still writes `--path api/`.
- One `--path` per path; order irrelevant. A directory covers everything under it.
- `*` matches `/` too: `'*.toml'` matches every `.toml` file.
- `'**/package.json'` matches only inside a directory; to include the top-level one, `':(glob)**/package.json'`.
- Exclude with `':(exclude)PATH'`: `--path scripts/ --path ':(exclude)scripts/fixtures/'`.
- Quote pathspecs containing `*`, `:(`, or `!`.
- Path matching no file: runs uncached and prints the path, so a typo never causes a skip.

A missing path makes the gate skip when it must run, hiding a real failure. List everything git tracks that the command reads:

- Source and test directories it checks.
- Lock files and manifests: `requirements.txt`, `uv.lock`, `package.json`, `pnpm-lock.yaml`, `Cargo.lock`, `go.sum`.
- Tool config: `pyproject.toml`, `tsconfig*.json`, `.eslintrc*`, `vitest.config.*`.
- Shared fixtures, schemas, generated contracts from other parts of the repository.
- The script, package file, or task-runner file defining the gate.

Unsure whether the command reads a file: include it. Extra path costs one unneeded run; missing path hides a failure.

Command reads the whole repository (spell check of all files, hook runner with `--all-files`): do not scope it.

Change makes a scoped gate read a path outside its list: add the path in the same change. Moving or renaming a path: update every list naming it.

## Git hooks

Works with prek and pre-commit 3.2+. Hook id `gate-cache`; `args` are the command line:

```yaml
repos:
  - repo: https://github.com/natelandau/gate-cache
    rev: v{{version}}
    hooks:
      - id: gate-cache
        name: test
        args: [--name, test, --, npm, test]
```

- Hook `args` get no shell. A name using `$(...)` must live in a script or recipe the hook calls.
- At commit time, gate-cache matches the staged content.
- The hook uses the developer's `PATH`. Tool installed only in the project (`.venv/bin`, `node_modules/.bin`): start with the project's runner (`npm test`, `bundle exec`, `uv run`) or a path such as `.venv/bin/pytest`.
- Project already runs checks from a script or recipe: prefer a local hook calling it, so commit, push, agents, and terminal share one command:

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

## Check a gate

After adding or changing a gate:

1. Run it. Must pass, with no `files changed during the run` or `matches no files`.
2. Run it again. Must print `already passed on`.
3. Scoped gate: edit a file outside its paths, run, must skip. Edit a file inside, run, must run. Revert both edits.
4. `gate-cache status` must list it as passed.

## Rules

- Never run `gate-cache clear` or `gate-cache stats clear` unless the user asks; both delete data permanently. `--yes` only when the user asked for the deletion. Show what would go with `--dry-run` first. After a tool upgrade affecting one gate, clear only it: `gate-cache clear --name NAME`.
- `gate-cache stats clear --all-repos` needs a person at a terminal to confirm. User wants it: ask them to run it.
- Never edit or delete files in `{{marker_dir}}` or `.git/gate-cache-locks/`.
- Never turn stats recording on or off unless the user asks.
- Trying stats or the dashboard on test data: set `GATE_CACHE_DATA_DIR` to a temporary directory and `GATE_CACHE_STATS=1` for that command, so the user's real stats stay untouched.
- Never set `GATE_CACHE_DISABLE=1` in a script, recipe, hook, shell profile, or committed file. It removes every skip.
- A wait can last up to the wait timeout (15 minutes by default). If your tool kills commands sooner, run the gate in the background or raise the tool's time limit; a smaller `--wait-timeout` also works. Never kill a waiting run or run the tool directly to avoid the wait.
- Never change `wait_timeout` or `wait_on_failure` or add `--wait-timeout 0` unless the user asks.
