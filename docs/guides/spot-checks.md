---
icon: lucide/shield-check
---

# Spot checks

gate-cache skips a gate when the gate already passed on the same files. That skip is correct only when the gate's name and paths cover everything the gate reads. A spot check tests that promise: now and then, gate-cache runs a gate that would skip, and confirms that it still passes.

## What you see

About one run in 50 of a gate that would skip runs its command instead. gate-cache prints this line first:

```text
gate-cache: pytest passed on tree 3be22be77da4, spot-checking (1 in 50)
```

A spot check is an ordinary run. gate-cache exits with the exit code of the command, so a spot check can make a commit hook or a CI step fail. When the command passes, gate-cache records a new pass, and later runs skip as before.

## When a spot check fails

If the command fails, gate-cache deletes the record of the earlier pass and prints a second line:

```text
gate-cache: pytest failed a spot check on tree 3be22be77da4, where it passed before. ...
```

The next run executes the command. The failure is real, so fix the cause. Do not run the gate again to get a skip.

A spot check that fails has one of two causes:

- **A flaky test.** The same files gave two results. The gate needs a fix, not the cache.
- **A missing input.** The gate reads something that its name and paths do not cover, and that input changed after the gate passed. Examples are an ignored file, an environment variable, or the version of a tool.

To cover a missing input, put it in the gate name after an `@`, or add its path with `--path`. Read [Cover inputs that git does not see](write-a-gate.md#cover-inputs-that-git-does-not-see) and [Scope a gate to paths](scope-to-paths.md).

If the command exits 0 but changes files, gate-cache also deletes the earlier pass, so the next run executes the command.

If you record stats, the dashboard counts spot checks on the Overview and lists each gate that failed one on the [Triage](../stats/triage.md) page. `gate-cache stats report` also lists the failed spot checks of each gate.

## Change the rate

The `spot_check_one_run_in` key of the [configuration file](../reference/configuration.md) sets the rate for every run. The `GATE_CACHE_SPOT_CHECK_ONE_RUN_IN` environment variable sets it for one shell and wins over the file.

| Value | Effect |
| --- | --- |
| `50` | About one run in 50 of a gate that would skip runs anyway. This is the default. |
| `0` | No spot checks. Every gate that already passed skips. |
| `1` | Every run of a gate that would skip runs anyway. |

To check one run, add `--spot-check` before `--`:

```bash
gate-cache --spot-check --name pytest -- pytest
```

The first line then ends with `(requested)`.
