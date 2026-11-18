---
icon: lucide/ruler
---

# Metrics

This page defines each number on the dashboard. Each number counts the runs in the time range and the repositories that you picked.

Each run has one outcome:

Skip
:   The gate already passed with the same hash, so the command did not run.

Pass
:   The command exited 0.

Fail
:   The command exited with a code other than 0.

Uncached
:   The command ran without the cache, such as in CI or with `GATE_CACHE_DISABLE=1`.

## Runs and time

Gate calls
:   Every recorded run, of every outcome.

Time gates ran
:   The total run time of the commands that ran, failures included. Skips add nothing.

Time saved by cache
:   For each skip, the run time of the pass that it matched.

Net saved by cache
:   Time saved by the cache, less the time that gate-cache took to decide and the time that runs waited for other runs. It can be negative when the cache cost more than it saved.

Cache skip rate
:   Skips divided by the runs that checked the cache. Uncached runs are not part of it.

Runs that waited
:   The runs that waited for another run of the same gate to finish, and how long they waited.

## Run time of a gate

Average, median, and p90 run
:   The run times of passing runs only. Half of the runs took no longer than the median, and nine of ten took no longer than the p90. The p90 needs at least 5 passing runs.

CPU/wall
:   The CPU time of the command divided by its run time. A value near 1× means that the gate used one core.

Peak memory
:   The highest memory use of a run.

Gates getting slower
:   The gates whose median passing run time is higher than in the previous period. Each period needs at least 5 passing runs.

## Failures

Gate failures
:   The runs that failed.

Lost to failures
:   The total run time of the runs that failed.

Early and late failures
:   A failure is early when it ended before half of the median passing run time of its gate. Any other failure is late.

Flaky gates
:   The gates that both failed and passed with the same hash. A different value after the `@` in the name counts as a different gate. Read [Find flaky gates](flaky-gates.md).

## Periods

Each number on the overview shows its change against the previous period of the same length. The dashboard hides the change when the previous period starts before your stats do, or more than 365 days ago.

Days start and end in the time zone of your browser. Weeks start on Sunday.

The dashboard keeps runs for 365 days.
