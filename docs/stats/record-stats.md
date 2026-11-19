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

The setting is for your user account on this computer, not for one repository. Every repository where you run gate-cache then records its runs.

To see whether recording is on and where the data is, run `gate-cache stats`:

```console
$ gate-cache stats
  recording:  on
  decided by: config
  config:     /home/dev/.config/gate-cache/config.toml
  data:       /home/dev/.local/state/gate-cache
```

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
3. The setting that `gate-cache stats on` and `gate-cache stats off` write.
4. Off.

Recording never changes whether a command skips, its exit code, or its output.

## Delete the data

```sh
gate-cache stats clear
```

This command permanently deletes all recorded stats. It asks you to type `yes` first. In a script, give `--yes`. It does not delete the records of passes that make gates skip. Read [Privacy](../privacy.md) for what gate-cache records.

## Keep test data apart

To try the dashboard without changes to your real stats, use a temporary data directory:

```sh
GATE_CACHE_DATA_DIR=/tmp/gate-cache-test GATE_CACHE_STATS=1 gate-cache dashboard
```

[Configuration](../reference/configuration.md) shows how to move the data directory for good.
