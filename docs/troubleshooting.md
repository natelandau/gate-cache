---
icon: lucide/life-buoy
---

# Troubleshooting

To run every command in full while you find the cause, set `GATE_CACHE_DISABLE=1`. To see which gates passed with the current hash of your files, run `gate-cache status`.

## A gate never skips

??? question "The command prints `files changed during the run, not recording pass`"

    The command passed but changed a file that git does not ignore, so gate-cache recorded no pass.

    - If the command is a formatter or a fixer, wrap the form that only checks, such as `prettier --check .` in place of `prettier --write .`.
    - If the command writes a report or a cache, such as `coverage.xml` or a test cache folder, add that file to `.gitignore`.

    To find the file, run `git status` after the command.

??? question "The gate name changes on each run"

    Without `--name`, the command line is the name. A command line that holds a date, a random value, or an absolute path to the worktree gives a new gate on each run or in each worktree. Give the gate a fixed `--name`, or use relative paths.

    Run `gate-cache status` to see the names that ran.

??? question "The command prints `running without cache`"

    The reason before the message names the cause:

    - `caching disabled in CI`: the `CI` variable is on. Read [CI](guides/ci.md).
    - `--path ... matches no files`: correct the path.
    - A merge conflict, a sparse checkout, or a submodule that is not checked out or has local changes: gate-cache cannot hash the files until you fix the state of the repository.

??? question "Someone runs the tool directly"

    A direct run, such as `pytest` in place of `gate-cache --name test -- pytest`, does not use the cache and records no pass. Make sure that people, hooks, and agents run the same gate-cache command. [Coding agents](guides/coding-agents.md#tell-your-agents-to-use-the-gates) shows what to tell agents.

??? question "A gate skips in my terminal, but not in my hook"

    Make sure that the hook and the terminal give the same name. Without `--name`, the command line is the name, so a hook that runs the command with other options is a different gate. A hook that runs the same command as your terminal avoids this. Read [Git hooks](guides/git-hooks.md).

## A gate skips when it must run

??? question "An input that gate-cache does not see changed"

    gate-cache sees only the content of the files that git does not ignore. After a change outside those files, such as a tool upgrade, a changed environment variable, a change to an ignored file, or a change to a service, a gate can skip with an old result.

    - For one run, set `GATE_CACHE_DISABLE=1`.
    - To delete every record of a pass for the repository, run `gate-cache clear`.
    - To make the gate run again whenever the input changes, put the input in the name. Read [Write a gate](guides/write-a-gate.md#cover-inputs-that-git-does-not-see).

??? question "A scoped gate misses a change"

    The gate reads a file that is not in its `--path` list. Add the path. Read [Scope a gate to paths](guides/scope-to-paths.md#choose-the-paths).

## A run waits

??? question "The command prints `is running in ... waiting`"

    Another run of the same gate with the same hash is in progress, maybe in another worktree or another agent session. The run is not stuck. When the other run passes, this run skips. A run waits at most 15 minutes.

    If a tool stops the command before the wait ends, run the gate in the background, raise the time limit of the tool, or give a smaller `--wait-timeout`.

## Git hooks

??? question "The hook fails with exit code 127, or uses the wrong tool version"

    The gate-cache hook starts the command with the `PATH` of git. A tool that is installed only in the project, such as in `.venv/bin`, is not on that `PATH`. Start the command with the command that your project uses to run its tools, such as `npm test`, or with a path such as `.venv/bin/pytest`. Read [Git hooks](guides/git-hooks.md#find-the-tools-of-the-command).

## The dashboard

??? question "The dashboard says that it has no UI"

    Only the copy of gate-cache from PyPI includes the dashboard. A copy that a git hook installs, or a copy from a git URL or a local path, does not. Install gate-cache from PyPI, as [Install](get-started/install.md) shows, and run the dashboard from that copy.

??? question "The dashboard shows no runs"

    Run `gate-cache stats` and make sure that recording is on. gate-cache records only runs that start after you turn recording on, and it records nothing in CI. Also check the time range and the repository filter at the top of the dashboard.

??? question "The dashboard opens on a port other than 7878"

    Another program uses port 7878, so the dashboard picked a free port. To pick a port, give `--port N`.
