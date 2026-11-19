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

`gate-cache stats` shows where the file is. By default, it is `~/.config/gate-cache/config.toml` on Linux and `~/Library/Application Support/gate-cache/config.toml` on macOS. gate-cache creates it when you run `gate-cache stats on` or `gate-cache stats off`. The new file lists every setting with a comment that says what it does. Only `stats_enabled` is active, and the other settings are commented out at their default values.

```toml title="config.toml"
stats_enabled = true # (1)!
stats_data_dir = "~/gate-cache-stats" # (2)!
wait_timeout = 300 # (3)!
wait_on_failure = "report" # (4)!
spot_check_one_run_in = 50 # (5)!
```

1.  Whether to record stats. `gate-cache stats on` and `gate-cache stats off` write this value.
2.  The directory for recorded stats. A relative path starts from the directory of the configuration file.
3.  The longest wait for another run of the same gate, in whole seconds. `0` never waits. The default is 900.
4.  What to do when the run that this run waited for failed. `rerun` runs the command. `report` exits with the failure. The default is `rerun`.
5.  How often a gate that would skip runs anyway, as one run in this many. A whole number. `0` turns spot checks off, and `1` checks every run that would skip. The default is 50. Read [Spot checks](#spot-checks).

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

## Spot checks

About one run in 50 of a gate that would skip runs its command instead, and gate-cache prints `NAME passed on tree HASH, spot-checking (1 in 50)` first. This run is a spot check. It confirms that a recorded pass still holds. A skip of a command that would fail hides a real failure, and a spot check finds that kind of skip.

A spot check is an ordinary run. gate-cache exits with the exit code of the command and records a new pass when the command passes.

If the command fails, or exits 0 but changes files, gate-cache deletes the record of the earlier pass, so the next run executes the command. A failure is real. Fix the cause. Do not run the gate again to get a skip.

A failure on a gate that is not flaky means that the gate reads something that its name and paths do not cover. Examples are an ignored file, an environment variable, or the version of a tool. Put that input in the name after an `@`, or add its path with `--path`. Read [Cover inputs that git does not see](../guides/write-a-gate.md#cover-inputs-that-git-does-not-see) and [Scope a gate to paths](../guides/scope-to-paths.md).

To change the rate, set `spot_check_one_run_in` in the configuration file, or set `GATE_CACHE_SPOT_CHECK_ONE_RUN_IN` for one shell. The variable wins over the file. Set the value to `0` to turn spot checks off. To check one run, add `--spot-check` to the command line. The line then ends with `(requested)`.

## Where gate-cache writes files

[File locations](file-locations.md) lists every file that gate-cache writes, and how to remove them.
