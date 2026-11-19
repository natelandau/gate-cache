---
icon: lucide/settings
---

# Configuration

gate-cache works with no configuration. Environment variables change one run or one shell. The configuration file changes every run for your user account.

## Environment variables

| Variable | Effect | Default |
| --- | --- | --- |
| `GATE_CACHE_DISABLE` | When on, runs every command without the cache. When `0` or `false`, keeps the cache on in CI. | Not set |
| `CI` | When on, turns off the cache and stats recording. Most CI systems set it. | Not set |
| `GATE_CACHE_MAX_AGE_DAYS` | The number of days that a record of a pass lasts. | `30` |
| `GATE_CACHE_STATS` | When on, records stats, even in CI. When `0` or `false`, does not record. | Not set |
| `GATE_CACHE_SPOT_CHECK_ONE_RUN_IN` | How often a gate that would skip runs anyway. Overrides `spot_check_one_run_in`. | `50` |
| `GATE_CACHE_DATA_DIR` | The directory for recorded stats. | Read [below](#stats) |

A variable is on when its value is not empty, `0`, or `false`. Case and spaces around the value do not matter.

## The configuration file

`gate-cache stats` shows where the file is. By default, it is `~/.config/gate-cache/config.toml` on Linux and `~/Library/Application Support/gate-cache/config.toml` on macOS. gate-cache creates it when you run `gate-cache stats on` or `gate-cache stats off`. The new file lists every setting with a comment that says what it does. Only `stats_enabled` is active. The other settings are commented out at their default values:

```toml title="config.toml"
# gate-cache settings. Environment variables override these values.
# https://natelandau.github.io/gate-cache/reference/configuration/

# Record run stats for the dashboard. `gate-cache stats on` and `stats off` set this.
stats_enabled = true

# The directory for recorded stats. A relative path starts from this file's directory.
# stats_data_dir = "~/gate-cache-stats"

# The longest wait, in whole seconds, for another run of the same gate. 0 never waits.
# wait_timeout = 900

# What to do when the run this run waited for failed: "rerun" runs the command,
# "report" exits with that failure.
# wait_on_failure = "rerun"

# Run about 1 in N runs that would skip, to check that the skip is still right. 0 turns this off.
# spot_check_one_run_in = 50

# Settings for one project. A table wins over the settings above for each repository
# that its pattern matches. A pattern that starts with / or ~ matches the folder of the
# repository. Any other pattern matches its remote, such as github.com/owner/repo.
# * matches any characters. If several patterns match, the most specific one wins.
# [projects."github.com/owner/*"]
# wait_timeout = 1200
# stats_enabled = false
```

To change a setting, remove the `#` at the start of its line and edit the value. Read [Spot checks](../guides/spot-checks.md) for how spot checks work and how to change their rate.

If a value is not valid, gate-cache prints a warning and uses the next setting that applies, or the default.

### Settings for one project

A `[projects."PATTERN"]` table sets values for the repositories that its pattern matches. A value in a matching table wins over the same key at the top of the file. A key that the table does not set comes from the top of the file. Environment variables and command options win over both.

```toml
wait_timeout = 300

# Every repository of the acme organization on GitHub
[projects."github.com/acme/*"]
wait_timeout = 1200

# One repository in a folder on this computer
[projects."~/work/big-monorepo"]
stats_enabled = false
spot_check_one_run_in = 10
```

A pattern matches one of two things:

- A pattern that starts with `/` or `~` matches the folder of the repository. It also matches every git worktree of that repository. For a bare repository, the pattern names the folder of the bare repository.
- Any other pattern matches the remote of the repository, in the form `HOST/OWNER/REPO`. gate-cache uses the `origin` remote, or the first remote when there is no `origin`. A repository without a remote matches only folder patterns.

In a pattern, `*` matches any characters, `/` included. If more than one table matches, the most specific pattern wins. A pattern without `*` wins over a pattern with `*`, and a pattern with more fixed characters wins over one with fewer. The order of the tables in the file does not matter.

Put all tables at the end of the file. TOML puts each key below a table heading into that table.

### Stats

The data directory comes from the first of these that applies:

1. `GATE_CACHE_DATA_DIR`, when it has a value.
2. `stats_data_dir` in the configuration file.
3. The default: `~/.local/state/gate-cache` on Linux and `~/Library/Application Support/gate-cache` on macOS.

A leading `~` expands to your home directory.

If a `[projects]` table sets `stats_data_dir`, the runs of those repositories go to that directory. The dashboard and the `gate-cache stats` commands read the directory that applies in the folder where you start them.

### Wait for a run in progress

The `wait_timeout` and `wait_on_failure` keys set the wait for every run, or for the runs of one project in a `[projects]` table. The `--wait-timeout` and `--on-wait-failure` options override it for one run.

- Raise `wait_timeout` if a gate takes longer than 15 minutes, so that a waiting run does not start a second copy before the first one ends.
- Lower `wait_timeout` if your coding agent stops commands after a shorter time.
- Set `wait_on_failure = "report"` if your slow gates seldom fail by chance. A waiting run then reports a failure at once, instead of running the gate again.

Read [Coding agents](../guides/coding-agents.md#several-agents-at-the-same-time).

## Where gate-cache writes files

[File locations](file-locations.md) lists every file that gate-cache writes, and how to remove them.
