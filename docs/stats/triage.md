---
icon: lucide/shuffle
---

# Triage gates

The **Triage** page of the dashboard lists the gates that need a look. A gate is one named lint or test command that gate-cache runs. Each row names one gate and one reason. If a gate has two reasons, it gets two rows. The newest rows come first. You need [stats recording](record-stats.md) on.

## Open the page

1. Run `gate-cache dashboard`.
2. Click **Triage** in the sidebar. The number beside it is the count of rows for the selected repositories and dates.
3. Optional: to see one reason only, pick it in the **Reason** list.

The **Flaky gates** card on the overview also links to this page, with the **Flaky** reason picked.

## Reasons

Each row has a badge that names its reason, one line that says what to check, and the runs that put the gate on the list.

| Reason | What it means | What the row shows |
| --- | --- | --- |
| **Flaky** | The gate failed and then passed on identical files, that is, with the same hash. Or a test passed only when the test tool ran it again. | Each such hash, with its runs, oldest first. For a gate that records its test reports, also the flaky tests and the tests that passed on a retry. |
| **Failed spot check** | The gate passed on a hash, then failed when gate-cache ran it again on the same hash to confirm the cache. | Each failed spot check, with its time, hash, and exit code. |

Spot checks do not count toward the **Flaky** reason. A failed spot check has its own row.

## Fix a flaky gate

A flaky gate gives different results on the same code. Flaky gates cost time, and they teach people and agents to ignore failures. Use the pattern of the runs to find the cause.

| What you see | A likely cause |
| --- | --- |
| A failure, then a pass a few minutes later | A test that depends on timing, order, or a shared resource |
| Failures only from one source, such as CI or a coding agent | A difference in the environment of that source |
| Failures only on one computer | A local tool version or a local service |
| Failures that cluster at the same hours | A shared service that is busy or down at those times |

The Breakdown panel on the overview and the gate details show which sources and computers ran a gate.

To see which tests of a gate fail, record its test reports. Read [Find slow and flaky tests](test-detail.md).

!!! note "Changed values are different gates"

    A failure under `test@v20` and a pass under `test@v22` with the same hash do not make `test` flaky, because the value after the `@` changed.

## Fix a failed spot check

A failed spot check means that a skip of this gate was not safe. One of these is true:

- A test in the gate is flaky. Look for the causes in [Fix a flaky gate](#fix-a-flaky-gate).
- The gate reads an input that its name and paths do not cover, such as an environment variable, an ignored file, or the installed version of a tool. Put that input in the gate name, or add its path. Read [Cover inputs that git does not see](../guides/write-a-gate.md#cover-inputs-that-git-does-not-see) and [Scope a gate to paths](../guides/scope-to-paths.md).

A missing input can also make a gate look flaky. If a flaky gate fails only after a change outside the repository, look for a missing input first.
