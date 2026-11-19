---
icon: lucide/braces
---

# Report format

Three commands print JSON for scripts and coding agents: `gate-cache stats report --json`, `gate-cache stats --json`, and `gate-cache status --json`. This page lists the keys that each command prints. To read the report as text, use `gate-cache stats report` without `--json`.

The format is a public contract. Each command has a `schema` key, a whole number. A change that removes a key, renames a key, or changes the meaning of a value raises `schema`. A change that adds a key does not. Ignore keys that you do not know.

## Rules for all values

| Value | Rule |
| --- | --- |
| Times of day | UTC, in ISO 8601 form, such as `2026-11-18T14:03:22Z`. Trend buckets start on a date in the time zone of the computer, such as `2026-11-18`. |
| Durations | Seconds, as numbers. |
| Memory | Bytes, as numbers. |
| Rates and ratios | Numbers from 0 to 1. A `change` is the relative growth, so `0.5` is 50 percent slower. |
| Missing values | `null`. A key never disappears, except where this page says that it does. |
| Lists in the one-gate view that can be long | An object with `total` (the items that exist), `shown` (the items in the list), and `items`. `--limit N` sets the most items. If `shown` is less than `total`, the list is cut. |
| `gates` in the suite view | A plain list with every gate. `--limit` does not cut it. |

A tree is the hash that gate-cache computes from the content of the files that git does not ignore. A gate skips only when it passed before on the same tree.

The report groups gates with keys, such as `test@v20` and `test@v22`, under the name `test`. The keyed names are its variants.

## Suite view

`gate-cache stats report --json` prints this view. It has one row for each gate, the gate with the most time spent first.

```json
{
  "schema": 1,
  "repo": "/home/me/shop/.git",
  "repo_name": "shop",
  "window": {
    "since": "2026-10-19T14:03:22Z",
    "until": "2026-11-18T14:03:22Z",
    "days": 30.0
  },
  "totals": {
    "runs": 412,
    "skips": 301,
    "time_saved": 5120.4,
    "time_spent": 2310.8,
    "fail_time": 410.2,
    "overhead": 38.5,
    "spot_checks": 6,
    "spot_check_failures": 1
  },
  "gates": [
    {
      "name": "test",
      "command": "pytest -q",
      "paths": [],
      "runs": 240,
      "skip_rate": 0.62,
      "failures": 14,
      "median_run": 96.4,
      "p90_run": 131.0,
      "time_spent": 1904.3,
      "time_saved": 4410.0,
      "fail_time": 380.1,
      "last_run": "2026-11-18T13:58:09Z",
      "flaky": {
        "trees": 2,
        "fails": 4,
        "passes": 6,
        "last_seen": "2026-11-16T09:12:40Z"
      },
      "slowdown": { "before": 80.2, "now": 96.4, "change": 0.2 },
      "uncached": [
        { "outcome": "uncached", "reason": "files changed during the run", "count": 7 }
      ],
      "waits": {
        "waited": 12,
        "skipped": 9,
        "reported": 1,
        "ran": 2,
        "timed_out": 0,
        "total_wait": 310.0,
        "median_wait": 24.5
      },
      "tests": { "flaky": 3, "retried": 1, "report_problems": 0 },
      "spot_checks": { "run": 5, "failed": 1, "last_failed": "2026-11-17T10:21:05Z" }
    }
  ]
}
```

Keys of the top level:

| Key | Meaning |
| --- | --- |
| `schema` | The format version. |
| `repo`, `repo_name` | The repository that the report covers, or `null` when the report covers more than one. Each gate then has its own `repo` and `repo_name`. |
| `window` | The time range of the report. `days` is its length. |
| `totals` | The sums over the gates. `time_saved` is the time that skipped runs did not spend. `fail_time` is the time that failed runs spent. `overhead` is the time that gate-cache itself spent around the runs. `spot_checks` and `spot_check_failures` count the spot checks and the spot checks that failed. |
| `gates` | The gates, one row each. |
| `recording` | Present, and `false`, only when recording is off. The report then shows the runs that were recorded before. |

Keys of each gate:

| Key | Meaning |
| --- | --- |
| `name`, `command`, `paths` | The gate name, its newest command line, and its `--path` values. |
| `runs`, `skip_rate`, `failures` | The runs in the window, the share that skipped, and the runs that failed. |
| `median_run`, `p90_run` | The median and the 90th percentile of the passing run times. `null` if there are too few runs. |
| `time_spent`, `time_saved`, `fail_time` | The time that the gate ran, the time that skips saved, and the time that failed runs spent. |
| `last_run` | The time of the newest run. |
| `flaky` | The hashes on which the gate both failed and passed: their count, the failed and passed runs on them, and the newest one. `null` if the gate is not flaky. |
| `slowdown` | The median run time before and now, if it grew since the window before. `null` otherwise. |
| `uncached` | Why runs did not skip, most common first. Each item has the `outcome`, the `reason`, and the `count`. |
| `waits` | How runs that waited for another run of the same gate ended, or `null` if none waited. `ran` counts the runs that then ran the command. |
| `tests` | Test counts from the reports that `--junit` records: the `flaky` tests, the tests that passed on a `retried` run, and the recent runs with a `report_problems` problem, such as a missing report. `null` if the gate never recorded test results and has no report problem. |
| `spot_checks` | The [spot checks](../guides/spot-checks.md) of the gate: `run` and `failed` count them, and `last_failed` is the time of the newest failure, or `null`. `spot_checks` is `null` if no spot check ran. A failed spot check means that a skip was not safe. |

The run counts, `failures`, and the times include spot checks. The flaky and retried counts do not, because a failed spot check can come from an input that the gate does not watch, not from a flaky test.

## One-gate view

`gate-cache stats report --name NAME --json` prints this view. `--limit` cuts its lists as the rules above say.

```json
{
  "schema": 1,
  "repo": "/home/me/shop/.git",
  "repo_name": "shop",
  "name": "test",
  "command": "pytest -q",
  "paths": [],
  "variants": {
    "total": 2,
    "shown": 1,
    "items": [
      {
        "name": "test@v22",
        "runs": 120,
        "last_run": "2026-11-18T13:58:09Z",
        "current": {
          "tree": "c81d1770d4ebf180f04cc0d92c03944a7e873595",
          "result": "hit",
          "last_run": null
        }
      }
    ]
  },
  "window": {
    "since": "2026-10-19T14:03:22Z",
    "until": "2026-11-18T14:03:22Z",
    "days": 30.0
  },
  "keyed": true,
  "current": null,
  "summary": {
    "runs": 240,
    "skip_rate": 0.62,
    "failures": 14,
    "median_run": 96.4,
    "p90_run": 131.0,
    "time_spent": 1904.3,
    "time_saved": 4410.0,
    "fail_time": 380.1,
    "cpu_ratio": 0.93,
    "peak_rss": 812646400,
    "median_rss": 640225280.0,
    "overhead": 21.7
  },
  "trend": {
    "bucket": "day",
    "items": [{ "start": "2026-11-18", "runs": 31, "median": 97.1, "p90": 128.4 }]
  },
  "failure_timing": {
    "threshold": 48.2,
    "early": { "runs": 3, "time": 21.0 },
    "late": { "runs": 9, "time": 301.5 },
    "unclassified": { "runs": 2, "time": 0.0 }
  },
  "exit_codes": { "1": 12, "137": 2 },
  "sources": {
    "total": 2,
    "shown": 1,
    "items": [
      { "source": "agent", "agent": "claude-code", "runs": 180, "failures": 11, "time_spent": 1500.2 }
    ]
  },
  "branches": {
    "total": 6,
    "shown": 1,
    "items": [{ "branch": "main", "runs": 120, "failures": 5 }]
  },
  "machines": {
    "total": 1,
    "shown": 1,
    "items": [
      { "machine": "563212e713ea4b2f87bbf7022fddbac2", "host": "laptop.local", "runs": 240, "failures": 14 }
    ]
  },
  "uncached": [],
  "waits": null,
  "flaky_trees": {
    "total": 1,
    "shown": 1,
    "items": [
      {
        "tree": "9a3f0c1d7e2b44a8b6d5e0f1c2a3b4c5d6e7f801",
        "fails": 2,
        "passes": 3,
        "last_seen": "2026-11-16T09:12:40Z",
        "runs": {
          "total": 5,
          "shown": 1,
          "items": [
            {
              "ts": "2026-11-16T09:01:12Z",
              "name": "test",
              "outcome": "fail",
              "exit_code": 1,
              "duration": 88.0,
              "tree": "9a3f0c1d7e2b44a8b6d5e0f1c2a3b4c5d6e7f801",
              "commit": "1288460",
              "branch": "main",
              "source": "agent",
              "agent": "claude-code",
              "machine": "563212e713ea4b2f87bbf7022fddbac2",
              "spot_check": false,
              "failed_tests": {
                "total": 1,
                "shown": 1,
                "items": ["tests/test_cart.py::test_checkout_total"]
              }
            }
          ]
        }
      }
    ]
  },
  "recent": {
    "total": 240,
    "shown": 1,
    "items": [
      {
        "ts": "2026-11-18T13:58:09Z",
        "name": "test",
        "outcome": "pass",
        "exit_code": 0,
        "duration": 95.2,
        "tree": "c81d1770d4ebf180f04cc0d92c03944a7e873595",
        "commit": "1288460",
        "branch": "main",
        "source": "terminal",
        "agent": null,
        "machine": "563212e713ea4b2f87bbf7022fddbac2",
        "spot_check": false,
        "failed_tests": null
      }
    ]
  },
  "spot_checks": {
    "run": 5,
    "failed": 1,
    "failures": {
      "total": 1,
      "shown": 1,
      "items": [
        {
          "ts": "2026-11-17T10:21:05Z",
          "name": "test",
          "outcome": "fail",
          "exit_code": 1,
          "duration": 91.3,
          "tree": "4b1e9d0c2a7f63e85d1c0b9a8f7e6d5c4b3a2918",
          "commit": "7d0e2c1",
          "branch": "main",
          "source": "hook",
          "agent": null,
          "machine": "563212e713ea4b2f87bbf7022fddbac2",
          "spot_check": true,
          "failed_tests": {
            "total": 1,
            "shown": 1,
            "items": ["tests/test_config.py::test_reads_env"]
          }
        }
      ]
    }
  },
  "tests": {
    "since": null,
    "slowest": {
      "total": 412,
      "shown": 1,
      "items": [
        { "name": "tests/test_search.py::test_full_index", "median": 12.4, "runs": 180, "share": 0.13 }
      ]
    },
    "flaky": {
      "total": 3,
      "shown": 1,
      "items": [
        { "name": "tests/test_cart.py::test_checkout_total", "fails": 2, "passes": 3, "last_seen": "2026-11-16T09:01:12Z" }
      ]
    },
    "retried": {
      "total": 1,
      "shown": 1,
      "items": [
        { "name": "tests/test_api.py::test_timeout", "runs": 4, "last_seen": "2026-11-17T15:40:02Z" }
      ]
    },
    "report_problems": { "missing": 0, "stale": 0, "unreadable": 0 }
  }
}
```

The example is trimmed to one item in each list, so `shown` is 1 where `total` is larger. Keys that the suite view explains, such as `uncached` and `waits`, have the same shape here.

| Key | Meaning |
| --- | --- |
| `variants` | The keyed names of the gate, newest run first. Each item has `name` (the full keyed name, such as `test@v22`), `runs`, `last_run` (the time of its newest run), and `current` (its own status, in the shape of the top-level `current`). |
| `keyed` | `true` when the gate has keyed names anywhere in the record, even when none ran in the window. |
| `current` | Whether the gate would skip on the current content: `result` is `hit` or `miss`. On a `miss`, `last_run` is the newest run on that content that did not record a pass, with its `exit_code`, `reason`, and `timestamp`, or `null` if there is none. On a `hit`, `last_run` is `null`. `current` is `null` for a gate with variants, because each variant has its own status, and when the content is unknown. |
| `summary` | The totals of the gate. `cpu_ratio` is CPU time divided by run time. `peak_rss` and `median_rss` are the memory of the command in bytes. |
| `trend` | The median and 90th percentile of the passing run times, in `day`, `week`, or `month` buckets. |
| `failure_timing` | Failed runs split by when they failed. Runs shorter than `threshold` seconds are `early`, the others are `late`. When the gate has no passing run in the window, `threshold` is `null` and every failed run is `unclassified`. |
| `exit_codes` | How often each exit code ended a failed run, most common first. The keys are strings. |
| `sources`, `branches`, `machines` | The runs and failures by what started them, by branch, and by computer, most runs first. `agent` is the name of the coding agent, or `null`. |
| `flaky_trees` | Each hash on which the gate both failed and passed, with its runs. |
| `recent` | The newest runs, newest first. |
| `spot_checks` | The number of [spot checks](../guides/spot-checks.md) that ran and failed, and in `failures`, the spot checks that failed, newest first. `null` if no spot check ran. |
| `tests` | The results of each test, from the reports that `--junit` records. `null` if the gate never recorded test results and has no report problem. The keys are below. |

A run has these keys: `ts`, `name`, `outcome`, `exit_code`, `duration`, `tree`, `commit`, `branch`, `source`, `agent`, `machine`, `spot_check`, and `failed_tests`. The `outcome` is one of these: `pass` (the command ran and passed, and gate-cache recorded the pass), `fail` (the command ran and failed), `skip` (the gate already passed on the tree, so the command did not run), `uncached` (the command ran with caching off), or `pass_unrecorded` (the command passed, but gate-cache could not record the pass, for example because files changed during the run). `exit_code` and `duration` are `null` for a run that did not run the command. `spot_check` is `true` for a run that gate-cache made to check a skip. `failed_tests` lists the names of the tests that failed in a failed run, at most 5, with `total` and `shown`. It is `null` when the run passed or recorded no test results. A failed run whose test results hold no failed test, such as a run that failed a coverage check, has a `total` of 0.

Keys of `tests`:

| Key | Meaning |
| --- | --- |
| `since` | gate-cache keeps the results of each test for 90 days, and the runs for 365 days. When the window starts earlier than 90 days ago, `since` is the time where the test results start, and the test numbers cover only that part of the window. Otherwise `null`. |
| `slowest` | The tests with the longest median passing time, slowest first, from the last 200 runs with test results. `share` is that time divided by the median run time of the gate, or `null` when the gate has no passing run. |
| `flaky` | The tests that both failed and passed on the same tree, newest first, with their `fails`, `passes`, and `last_seen`. |
| `retried` | The tests that failed and then passed when the test tool ran them again in the same run, newest first. `runs` counts those runs. |
| `report_problems` | Of the last 20 runs that ran the command, the number with a `missing`, `stale`, or `unreadable` report. Read [Fix a report problem](../stats/test-detail.md#fix-a-report-problem). |

## Recording view

`gate-cache stats --json` prints whether recording is on.

```json
{
  "schema": 1,
  "enabled": true,
  "decided_by": "config",
  "config_file": "/home/me/.config/gate-cache/config.toml",
  "data_dir": "/home/me/.local/share/gate-cache"
}
```

`decided_by` is `env`, `ci`, `config`, or `default`. It names the first setting that decided the value. Read [Record stats](../stats/record-stats.md).

## Status view

`gate-cache status --json` prints the pass status of the current content. It has the same `schema` key. Without a name, it has `passed` and `missed` in place of the name keys. With `--path`, it adds `paths` and `full_tree`.

```json
{
  "schema": 1,
  "enabled": true,
  "name": "test",
  "tree": "c81d1770d4ebf180f04cc0d92c03944a7e873595",
  "reason": null,
  "marker": "/home/me/shop/.git/gate-cache/30ebddb40a1db94576522b60726a4357a87b8af6fb32d43e2a0f6259ef9b19bc",
  "result": "hit",
  "last_run": null,
  "duration": 95.2
}
```

When `last_run` is not `null`, it is an object with `exit_code`, `reason`, and `timestamp`.

## Exit codes

The exit codes of `gate-cache stats report` are in the [command reference](commands.md#exit-codes).
