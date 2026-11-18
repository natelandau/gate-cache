---
icon: lucide/workflow
---

# CI

In CI, gate-cache runs every command and records nothing. CI is the check that a team relies on before it merges, so its result never depends on a record from an earlier run. You do not need to change your CI jobs to remove gate-cache from them.

gate-cache turns off the cache when the `CI` environment variable is on. Most CI systems set `CI=true` in every job, for example GitHub Actions and GitLab CI/CD. Jenkins does not set `CI`.

A variable is on when its value is not empty, `0`, or `false`. Case and spaces around the value do not matter.

## Turn the cache on or off

`GATE_CACHE_DISABLE` overrides `CI`.

| To | Set |
| --- | --- |
| Keep the cache on in CI | `GATE_CACHE_DISABLE=0` |
| Turn the cache off outside CI | `GATE_CACHE_DISABLE=1` |

Keep the cache on in CI only on a runner that keeps the repository between jobs. For example, if one job runs the tests and a later job on the same checkout runs them again before a deploy, the later job can skip.

!!! note "A fresh clone has nothing to skip"

    gate-cache stores its records of passes in the `.git` directory. A CI runner that starts from a fresh clone has no records, so it runs every command even with the cache on. The cache helps in CI only when the runner keeps the `.git` directory between jobs.

## Record stats in CI

Stats recording is also off in CI. To record the runs of a CI job, set `GATE_CACHE_STATS=1`. The stats stay on the runner, so this is useful only on a runner that you own. Read [Record stats](../stats/record-stats.md).
