---
icon: lucide/coins
---

# Cut what your checks cost

Each run of a check costs time: yours, your CI, and your coding agents. The dashboard shows where that time goes, so you can spend effort where it pays. You need [stats recording](record-stats.md) on.

## Find the expensive gates

- On the overview, the **Time gates ran** chart shows the run time per day of the gates that took the most time.
- **Top gates**, ranked by **Time ran**, lists the gates that ran the longest in total.
- On the **Gates** page, sort by **Time ran**.

A gate that is slow and runs often costs the most. Each run of a 5-minute suite that agents start 40 times a day costs more than three hours.

## Choose what to do

| What you see | What to try |
| --- | --- |
| A gate with a low skip rate | Scope the gate to the files that it reads, so that changes elsewhere do not make it run. Read [Scope a gate to paths](../guides/scope-to-paths.md). |
| The same gate run directly and through gate-cache | Make sure that everyone, including agents, runs the gate with the same gate-cache command. Read [Coding agents](../guides/coding-agents.md). |
| A gate whose run time grows | Open its details. The chart of passing run times shows when it started to slow down. **Gates getting slower** on the overview lists these gates. |
| A slow gate, with no clue which tests make it slow | Record its test reports. The gate details then list its slowest tests. Read [Find slow and flaky tests](test-detail.md). |
| High CPU per second of run time | The gate uses several cores. Running gates one after another can be faster than running them at the same time. |
| Much time lost to failures | Failures that end early are cheap. Failures late in a long run are expensive. Move the checks that fail most often to the start, or into a faster gate. |
| A flaky gate | Each flaky failure costs a full run again. Read [Triage gates](triage.md). |

## Measure the result

After a change, compare two periods. Each number on the overview shows its change against the previous period of the same length.
