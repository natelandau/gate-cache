---
icon: lucide/folder-open
---

# File locations

gate-cache writes files in three places: the `.git` directory of each repository, a configuration and data directory for your user account, and a temporary directory. It never changes your project files or your git index.

## In each repository

| Path | Holds | Deleted |
| --- | --- | --- |
| `.git/gate-cache/` | One small file for each pass of a gate, and a record of each failed run that `gate-cache status` shows. | After 30 days, or by `gate-cache clear`. |
| `.git/gate-cache-locks/` | One lock file for each gate that runs, so that a second run of the same gate can wait. | When gate-cache deletes old records, at most once a day. |

All worktrees of a repository use the `.git` directory of the main checkout, so they share these files. A fresh clone has none of them. `GATE_CACHE_MAX_AGE_DAYS` changes how long a record of a pass lasts. Read [Configuration](configuration.md).

## For your user account

`gate-cache stats` shows the paths that apply on your computer.

| What | Linux | macOS |
| --- | --- | --- |
| Configuration file | `~/.config/gate-cache/config.toml` | `~/Library/Application Support/gate-cache/config.toml` |
| Stats directory | `~/.local/state/gate-cache/` | `~/Library/Application Support/gate-cache/` |

If the `XDG_CONFIG_HOME` or `XDG_STATE_HOME` environment variable is set, gate-cache uses it in place of the default, on Linux and on macOS. `GATE_CACHE_DATA_DIR`, or `data_dir` in the configuration file, moves the stats directory.

gate-cache creates the configuration file when you run `gate-cache stats on` or `gate-cache stats off`.

### The stats directory

gate-cache writes to the stats directory when [stats recording](../stats/record-stats.md) is on, and when you open the dashboard.

| File | Holds |
| --- | --- |
| `events.jsonl` | The runs that gate-cache recorded since the dashboard last read them. |
| `stats.sqlite3`, and its `-wal` and `-shm` files | All the runs that the dashboard read, for up to 365 days. |
| `machine-id` | A random ID for your computer. |
| `dashboard.lock`, `dashboard.url` | Files that make sure that only one dashboard runs at a time. |
| `events.*.processing` | Runs that the dashboard is reading. |

`gate-cache stats clear` deletes the recorded runs: `events.jsonl`, `stats.sqlite3` with its `-wal` and `-shm` files, and the `.processing` files. It keeps `machine-id` and the dashboard files.

## Temporary files

To compute the hash of your files, gate-cache writes a private copy of the git index to a temporary directory, and deletes it when it has the hash. The directory is:

1. `$XDG_RUNTIME_DIR/gate-cache/`, if `XDG_RUNTIME_DIR` is set.
2. Otherwise, `/run/user/<user ID>/gate-cache/` on Linux and `~/Library/Caches/TemporaryItems/gate-cache/` on macOS.
3. If neither is available, as in many containers, a `gate-cache` directory in the temporary directory of the system.

If a run is killed, the next run deletes the leftover directory after one hour.

## Remove everything

To remove all the files of gate-cache:

1. In each repository, run `gate-cache clear` and delete `.git/gate-cache-locks/`.
2. Run `gate-cache stats clear`.
3. Delete the configuration file and the stats directory.
