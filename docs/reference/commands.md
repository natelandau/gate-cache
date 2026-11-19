---
icon: lucide/square-terminal
---

# Commands

Run `gate-cache --help` or `gate-cache COMMAND --help` for the options of the version that you installed.

## Run a gate

```sh
gate-cache [OPTIONS] -- COMMAND [ARGS...]
```

| Option | Effect |
| --- | --- |
| `--name NAME` | The name of the gate. Without it, the command line is the name. |
| `--path PATH` | Match only the files under this git pathspec. Give it once for each path. Read [Scope a gate to paths](../guides/scope-to-paths.md). |
| `--junit PATH` | With stats recording on, record the tests in this JUnit XML report, or in the `.xml` files directly in this folder, that the command writes. Give it once for each path. Read [Find slow and flaky tests](../stats/test-detail.md). |
| `--wait-timeout SECONDS` | The longest time to wait for another run of the same gate. `0` never waits. The default is 900. |
| `--on-wait-failure rerun\|report` | What to do when the run that this run waited for failed. `rerun` runs the command. `report` exits with the failure. The default is `rerun`. |
| `--spot-check` | Run the command even when it already passed with the current hash, as a spot check. Read [Spot checks](configuration.md#spot-checks). |

`--` is required. Only these options can come before it. gate-cache runs everything after `--` exactly as given, without a shell.

## `gate-cache status`

Shows which gates skip with the current hash of your files. It runs nothing. Use it before you commit or push, to see which gates will skip and which will run, or after a failure, to see which gates failed with the current hash.

| Form | Shows |
| --- | --- |
| `gate-cache status` | The gates that passed with the current hash, and the gates that failed with it. |
| `gate-cache status --name NAME` | One gate. |
| `gate-cache status -- COMMAND` | One gate that runs without `--name`. Give the same command line. |

Add the same `--path` options to look up a scoped gate. Add `--json` to print one JSON object in place of text.

## `gate-cache clear`

Permanently deletes every record of a pass for the repository, and the run times that the `usually` estimate uses, so every gate runs again in full. Use it after a change that gate-cache does not see, such as a tool upgrade. It asks you to type `yes` first. In a script, give `--yes`. It does not delete stats.

## `gate-cache stats`

| Command | Effect |
| --- | --- |
| `gate-cache stats` | Shows whether recording is on, what decided it, and where the configuration file and the data are. |
| `gate-cache stats on` | Turns recording on. |
| `gate-cache stats off` | Turns recording off and keeps the data. |
| `gate-cache stats clear` | Permanently deletes all recorded stats. It asks you to type `yes` first. In a script, give `--yes`. |

## `gate-cache dashboard`

Opens the stats dashboard in your browser. Read [The dashboard](../stats/dashboard.md).

| Option | Effect |
| --- | --- |
| `--port N` | Listen on this port only. Without it, the dashboard uses port 7878, or a free port when 7878 is in use. |
| `--no-browser` | Do not open a browser. |

Only one dashboard runs at a time. A second `gate-cache dashboard` opens the one that runs.

## Other options

| Option | Effect |
| --- | --- |
| `--prompt` | Prints a prompt that has a coding agent add gate-cache to a repository, or review its setup. |
| `--skill` | Prints the [guide for coding agents](agent-guide.md). |
| `--version` | Prints the version. |

## Exit codes

| Situation | Exit code |
| --- | --- |
| The command ran | The exit code of the command |
| The gate already passed, so the command did not run | 0 |
| The command is not found | 127 |
| The command cannot run | 126 |
| A signal stopped the command | 128 plus the signal number |
| An error in the gate-cache options | 2, and nothing runs |
| `status` found a pass | 0, else 1 |
| `clear` or `stats clear` was not confirmed, or failed | 1 |

An error in the cache never changes the exit code of the command.

## Messages

gate-cache writes its own lines to stderr, with the prefix `gate-cache:`. All other output comes from the command.

| Message | Meaning |
| --- | --- |
| `running NAME (usually 2m 10s)` | The command is about to run. The time is the middle value of the run times of the last 5 runs that exited 0. |
| `NAME already passed on tree HASH, skipping (saved 1m 34s)` | The gate passed before with the same hash, so the command did not run. The time is how long the command ran when it passed. |
| `NAME already passed on paths HASH, skipping` | The same, for a gate scoped to paths. Nothing under its paths changed. |
| `NAME is running in WORKTREE (started 1m 12s ago), waiting` | Another run of the gate with the same hash is in progress. This run waits for it. |
| `NAME still running in WORKTREE after 15m 0s, running anyway` | The wait reached its limit, so the command runs. |
| `NAME failed on tree HASH in WORKTREE (exit N), not running again` | With `--on-wait-failure report`, the run that this run waited for failed. |
| `files changed during the run, not recording pass` | The command exited 0 but changed files, so gate-cache recorded no pass. |
| `REASON, running without cache` | The command runs, and gate-cache records no pass. The reason names the cause, such as `caching disabled in CI`. |
| `warning: could not record pass: ...` | The command passed, but gate-cache could not record the pass. The exit code does not change. |

[Troubleshooting](../troubleshooting.md) tells you what to do about each message.
