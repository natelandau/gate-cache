---
icon: lucide/activity
---

# Record stats

gate-cache can record each run of a gate. A local dashboard then shows which gates are flaky, which gates are slow, and how much time your gates cost and the cache saves. The data stays on your computer.

!!! warning "Recording is opt-in"

    gate-cache records nothing until you turn recording on with `gate-cache stats on`. Until then, the dashboard has no data to show.

## Turn recording on

```sh
gate-cache stats on
```

The setting is for your user account on this computer, not for one repository. Every repository where you run gate-cache then records its runs. To turn recording off for some repositories, set `stats_enabled = false` in a [`[projects]` table](../reference/configuration.md#settings-for-one-project).

To see whether recording is on and where the data is, run `gate-cache stats`:

```console
$ gate-cache stats
recording   on
decided by  config
config      /home/dev/.config/gate-cache/config.toml
data        /home/dev/.local/state/gate-cache
```

When a `[projects]` table decides, the output also shows a `project` line with the pattern of that table.

To turn recording off, run `gate-cache stats off`. The data that you already recorded stays in place.

## Open the dashboard

```sh
gate-cache dashboard
```

The dashboard opens in your browser at `http://127.0.0.1:7878`. If that port is in use, it picks a free port. Press ++ctrl+c++ to stop it. Read [The dashboard](dashboard.md) for a tour.

!!! note

    A copy of gate-cache that the prek or pre-commit hook installs has no dashboard. Use a copy from PyPI. Read [Install](../get-started/install.md).

## Read the stats in a terminal

To print the stats in a terminal, run:

```sh
gate-cache stats report
```

The report shows each gate of the current repository. Add `--name NAME` to show one gate in detail. Add `--json` to print one JSON object for a script or a coding agent. Every copy of gate-cache has the report. Read [`gate-cache stats report`](../reference/commands.md#gate-cache-stats-report) for its options.

## What decides whether recording is on

The first of these that applies decides:

1. The `GATE_CACHE_STATS` environment variable, when it has a value. `0` or `false` turns recording off, and any other value turns it on.
2. The `CI` environment variable. When `CI` is on, recording is off.
3. `stats_enabled` in a `[projects]` table that matches the repository.
4. The setting that `gate-cache stats on` and `gate-cache stats off` write. If a `[projects]` table overrides that setting in the current repository, these commands say so.
5. Off.

Recording never changes whether a command skips, its exit code, or its output.

## Delete the data

```sh
gate-cache stats clear
```

This command permanently deletes the recorded stats of the current repository. It shows how many runs it deletes and asks you to type `yes` first. To see what it deletes without a deletion, add `--dry-run`. Stop the dashboard first, because the command does not run while the dashboard runs. It does not delete the records of passes that make gates skip.

To delete the stats of every repository on the computer, run `gate-cache stats clear --all-repos` in a terminal. This form always asks you to type `yes`, and it does not accept `--yes`. Read [Privacy](../privacy.md) for what gate-cache records.

## Keep test data apart

To try the dashboard without changes to your real stats, use a temporary data directory:

```sh
GATE_CACHE_DATA_DIR=/tmp/gate-cache-test GATE_CACHE_STATS=1 gate-cache dashboard
```

[Configuration](../reference/configuration.md) shows how to move the data directory for good.
