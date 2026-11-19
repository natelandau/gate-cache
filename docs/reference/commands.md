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
| `--path PATH` | Matches only the files under this git pathspec. Give it once for each path. Read [Scope a gate to paths](../guides/scope-to-paths.md). |
| `--junit PATH` | With stats recording on, records the tests in this JUnit XML report, or in the `.xml` files directly in this folder, that the command writes. Give it once for each path. Read [Find slow and flaky tests](../stats/test-detail.md). |
| `--wait-timeout SECONDS` | The longest time to wait for another run of the same gate. `0` never waits. The default is 900. |
| `--on-wait-failure rerun\|report` | What to do when the run that this run waited for failed. `rerun` runs the command. `report` exits with the failure. The default is `rerun`. |
| `--spot-check` | Runs the command even when it already passed with the current hash, as a spot check. Read [Spot checks](../guides/spot-checks.md). |

`--` is required. Only these options can come before it. gate-cache runs everything after `--` exactly as given, without a shell.

## `gate-cache status`

Shows which gates skip with the current hash of your files. It runs nothing. Use it before you commit or push, to see which gates will skip and which will run, or after a failure, to see which gates failed with the current hash.

| Form | Shows |
| --- | --- |
| `gate-cache status` | The gates that passed with the current hash, and the gates that failed with it. |
| `gate-cache status --name NAME` | One gate. |
| `gate-cache status -- COMMAND` | One gate that runs without `--name`. Give the same command line. |

Add the same `--path` options to look up a scoped gate. Add `--json` to print one JSON object in place of text. Read the [report format](report-format.md).

## `gate-cache clear`

Permanently deletes every record of a pass or a failed run for the repository, and the run times that the `usually` estimate uses, so every gate runs again in full. Use it after a change that gate-cache does not see, such as a tool upgrade. It does not delete stats.

Before it deletes, the command shows how many records it deletes and for which gates, and asks you to type `yes`. In a script, give `--yes`. If there is nothing to delete, it asks nothing and exits 0. If `--name` names a gate with no records, the command exits 1, so a typing error does not look like a success.

| Option | Effect |
| --- | --- |
| `--name NAME` | Deletes the records of one gate only. A name with an `@` key, such as `test@v22`, counts as part of the gate `test`. |
| `--dry-run` | Shows what the command deletes, and deletes nothing. |
| `--yes`, `-y` | Deletes without the question. |
| `--json` | Prints the result as one JSON object. Needs `--yes` or `--dry-run`. |

## `gate-cache stats`

| Command | Effect |
| --- | --- |
| `gate-cache stats` | Shows whether recording is on, what decided it, and where the configuration file and the data are. |
| `gate-cache stats on` | Turns recording on. |
| `gate-cache stats off` | Turns recording off and keeps the data. |
| `gate-cache stats report` | Prints a report of the recorded runs. |
| `gate-cache stats clear` | Permanently deletes the recorded stats of the repository. |

Add `--json` to `gate-cache stats`, `stats on`, or `stats off` to print the recording setting as a JSON object.

### `gate-cache stats report`

Prints, for each gate, its runs, skip rate, failures, run times, and the time it spent and saved. The report is for terminals and for coding agents. For a view in a browser, use the [dashboard](../stats/dashboard.md).

With `--name`, or a command after `--`, the report shows one gate in detail: its status on the current content, its trend, its exit codes, its flaky hashes, where its runs came from, and its recent runs. The report groups `test@v22` and `test@v20` under `test`, so give `--name test`. For a gate that ran without `--name`, give its command after `--`.

| Option | Effect |
| --- | --- |
| `--json` | Prints one JSON object. Read the [report format](report-format.md). |
| `--since DURATION` | Sets the length of the report window, counted back from `--until`, as a whole number and `h`, `d`, `w`, or `y`. The default is `30d`. For the week before the last one, give `--since 7d --until 7d`. |
| `--until WHEN` | Sets the end of the report: a date, an ISO 8601 timestamp, or a duration ago. The default is now. |
| `--limit N` | Sets the most items in each list, from 1 to 500. The default is 20. |
| `--repo NAME\|PATH` | Covers one repository, by the name that the report prints or a path inside it. |
| `--all-repos` | Covers every repository. |
| `--name NAME` | Reports one gate. |

Inside a repository, the report covers that repository. Outside a repository, it covers every repository on the computer. `--name` outside a repository needs `--repo`. If a `--repo` name matches more than one repository, use a path.

### `gate-cache stats clear`

Permanently deletes the recorded runs of the repository: their history, time saved, and skip rates. It does not delete the records of passes that make gates skip. It does not run while the dashboard runs.

Before it deletes, the command shows how many runs it deletes, of how many gates, and from which dates, and asks you to type `yes`. In a script, give `--yes`. If there is nothing to delete, it asks nothing and exits 0.

| Option | Effect |
| --- | --- |
| `--repo NAME\|PATH` | Deletes the stats of one repository, by the name that the report prints or a path inside it. The repository does not have to exist on the disk. |
| `--all-repos` | Deletes the stats of every repository on the computer. Only a person at a terminal can confirm it, so it does not accept `--yes` or `--json`. |
| `--dry-run` | Shows what the command deletes, and deletes nothing. |
| `--yes`, `-y` | Deletes without the question. |
| `--json` | Prints the result as one JSON object. Needs `--yes` or `--dry-run`. |

Outside a repository, give `--repo` or `--all-repos`.

## `gate-cache dashboard`

Opens the stats dashboard in your browser. Read [The dashboard](../stats/dashboard.md).

| Option | Effect |
| --- | --- |
| `--port N` | Listens on this port only. Without it, the dashboard uses port 7878, or a free port when 7878 is in use. |
| `--no-browser` | Does not open a browser. |
| `--json` | Prints the address as one line of JSON, then keeps the dashboard open. |

Only one dashboard runs at a time. A second `gate-cache dashboard` opens the one that runs.

## JSON output

Every command except the gate run takes `--json`. With `--json`, the command prints one JSON object to stdout in place of text, and an error also prints as a JSON object. The command never asks a question, so `clear` and `stats clear` need `--yes` or `--dry-run`. Read the [report format](report-format.md) for the keys.

`--json` after `--` belongs to the command that you give, not to gate-cache.

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
| `clear` or `stats clear` was not confirmed, or failed, or `clear --name` found no records of the gate | 1 |
| `stats on` or `stats off` could not write the setting | 1 |
| `stats report` ran, also when nothing was recorded | 0 |
| `stats report` found no such gate or repository, or could not read the record | 1 |
| `stats report` got a bad option, or a `--repo` name that matches more than one repository | 2 |
| `dashboard` stopped, or another dashboard already runs | 0 |
| `dashboard` could not start | 1 |

An error in the cache never changes the exit code of the command.

## Messages

When gate-cache runs a gate, it writes its own lines to stderr, with the prefix `gate-cache:`. All other output comes from the command.

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

The other commands write their results to stdout. They write an error to stderr as a line that starts with `error:`. A line that starts with `hint:` can follow, with the fix:

```text
error: --json needs --yes or --dry-run, because clear cannot ask for confirmation
  hint: gate-cache clear --dry-run --json
```
