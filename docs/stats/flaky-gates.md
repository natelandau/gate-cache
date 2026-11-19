---
icon: lucide/shuffle
---

# Find flaky gates

A flaky gate gives different results on the same code. It fails, you run it again with no change, and it passes. Flaky gates cost time, and they teach people and agents to ignore failures.

gate-cache marks a gate as flaky when it both failed and passed with the same hash, that is, on identical files. You need [stats recording](record-stats.md) on.

## Find them

1. Run `gate-cache dashboard`.
2. Look at the **Flaky gates** card on the overview, or open the **Flaky** page.

The Flaky page lists each flaky gate. Under each gate, it shows each hash with which the gate both failed and passed, with the runs on that tree, oldest first.

## Read the pattern

| What you see | A likely cause |
| --- | --- |
| A failure, then a pass a few minutes later | A test that depends on timing, order, or a shared resource |
| Failures only from one source, such as CI or a coding agent | A difference in the environment of that source |
| Failures only on one computer | A local tool version or a local service |
| Failures that cluster at the same hours | A shared service that is busy or down at those times |

The Breakdown panel on the overview and the gate details show which sources and computers ran a gate.

To see which tests of a gate fail, record its test reports. Read [Find slow and flaky tests](test-detail.md).

## Make sure it is not gate-cache

A gate also looks flaky when its result depends on an input that gate-cache does not see, such as an environment variable or the installed version of a tool. Put that input in the gate name. Read [Write a gate](../guides/write-a-gate.md#cover-inputs-that-git-does-not-see).

!!! note "Changed values are different gates"

    A failure under `test@v20` and a pass under `test@v22` with the same hash do not make `test` flaky, because the value after the `@` changed.
