---
icon: lucide/shield
---

# Privacy

gate-cache sends nothing to any server. Stats recording is off until you turn it on, and the data stays on your computer.

## Records of passes

To skip a gate, gate-cache stores a small file for each pass in the `.git` directory of the repository. The file holds the gate name, the command line, the hash of the files, the time, and the run time. It holds no file content and no command output. gate-cache also keeps the recent run times of each gate, with no other data. `gate-cache clear` deletes these files.

## Stats

When you [turn recording on](stats/record-stats.md), each run of a gate adds one event to a file in your data directory. An event holds:

- The gate name, its `--path` values, the command line, and the hash of the files.
- The outcome, the exit code, the run time, the CPU time, and the peak memory of the command.
- The time saved by a skip, and the time that the run waited for another run.
- The path of the repository and the worktree, the folder where the gate ran, the branch, the commit, and the URL of the remote, without user names or passwords.
- What started the run: CI, a git hook, a terminal, or a coding agent, with the name of the agent.
- The host name of the computer, its platform, and a random ID for the computer.
- The version of gate-cache.

If a gate has [`--junit`](stats/test-detail.md), each run that runs the command and finds a report from this run also stores the name, the result, and the run time of each test in the report. gate-cache stores no test output and no failure messages.

An event holds no command output and no file content.

!!! warning "Never put a secret in a gate name or a command line"

    gate-cache stores the gate name and the command line as plain text, in the records of passes and in the stats. The paths and the host name can also hold your user name.

`gate-cache stats clear` deletes all recorded stats. The dashboard keeps runs for 365 days, and the results of each test for 90 days.

## The dashboard

- The dashboard listens only on `127.0.0.1`, so other computers cannot reach it.
- It rejects requests for any other host name, and other sites cannot show it in a frame.
- Its one outside request loads a font from `cdn.jsdelivr.net`. That request sends no stats. Without a connection, the dashboard uses a system font.
