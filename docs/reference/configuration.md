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
```

To change a setting, remove the `#` at the start of its line and edit the value. Read [Spot checks](../guides/spot-checks.md) for how spot checks work and how to change their rate.

If a value is not valid, gate-cache prints a warning and uses the default.

### Stats

The data directory comes from the first of these that applies:

1. `GATE_CACHE_DATA_DIR`, when it has a value.
2. `stats_data_dir` in the configuration file.
3. The default: `~/.local/state/gate-cache` on Linux and `~/Library/Application Support/gate-cache` on macOS.

A leading `~` expands to your home directory.

### Wait for a run in progress

The `wait_timeout` and `wait_on_failure` keys set the wait for every run. The `--wait-timeout` and `--on-wait-failure` options override it for one run.

- Raise `wait_timeout` if a gate takes longer than 15 minutes, so that a waiting run does not start a second copy before the first one ends.
- Lower `wait_timeout` if your coding agent stops commands after a shorter time.
- Set `wait_on_failure = "report"` if your slow gates seldom fail by chance. A waiting run then reports a failure at once, instead of running the gate again.

Read [Coding agents](../guides/coding-agents.md#several-agents-at-the-same-time).

## Where gate-cache writes files

[File locations](file-locations.md) lists every file that gate-cache writes, and how to remove them.
