"""Compute the dashboard metrics from the archive."""

from __future__ import annotations

import json
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, get_args
from zoneinfo import ZoneInfo

from gate_cache.stats.archive import RETENTION_DAYS, tests_since
from gate_cache.stats.recorder import Outcome

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable, Iterable, Iterator, Sequence

    from gate_cache.stats.window import Bucket

_RAN = "('skip', 'pass', 'pass_unrecorded', 'fail')"
_GOOD = "('pass', 'pass_unrecorded')"
_RECENT_LIMIT = 50
_TOP_SPENT = 5
_MAX_PAGE = 500
_OUTCOMES: frozenset[str] = frozenset(get_args(Outcome))
# The archive keeps outcomes from newer gate-cache versions; only known ones count.
_KNOWN = "outcome IN (" + ", ".join(f"'{o}'" for o in sorted(_OUTCOMES)) + ")"
_ROW_COLUMNS = (
    "ts, repo, name, outcome, duration, saved, exit_code, reason, tree, reported, gate, spot_check"
)
# Every real UTC offset is a whole number of quarter hours, so no bucket spans two local days.
_BUCKET_SECONDS = 900
# Floor division: CAST truncates toward zero, which is one bucket too high for negative ts.
_BUCKET = (
    f"(CAST(ts / {_BUCKET_SECONDS} AS INTEGER)"
    f" - (ts < CAST(ts / {_BUCKET_SECONDS} AS INTEGER) * {_BUCKET_SECONDS}))"
)
# Fewer passes make a 90th percentile meaningless.
_MIN_SPREAD_RUNS = 5
_HISTOGRAM_BINS = 12
# A failure faster than this share of the median pass stopped before the gate did its real work.
_EARLY_FAIL_FRACTION = 0.5
_INTEGER_RE = re.compile(r"-?[0-9]+")
_TEST_PASSED = "('pass', 'retried')"
SLOWEST_TESTS_LIMIT = 20
# Bounds the per-test read: a busy gate can hold thousands of results per run.
SLOWEST_TESTS_RUNS = 200
REPORT_PROBLEM_RUNS = 20
FAILED_TESTS_SHOWN = 5
_REPORT_PROBLEMS = ("missing", "stale", "invalid")
# The report contract names each stored problem status; `invalid` reads as `unreadable` there.
_REPORT_PROBLEM_KEYS = {"missing": "missing", "stale": "stale", "invalid": "unreadable"}
_TESTS_CUTOFF_SLACK = 3600

# The cost of one gate over a range, as both report views show it.
SUMMARY_KEYS = (
    "runs",
    "skip_rate",
    "failures",
    "median_run",
    "p90_run",
    "time_spent",
    "time_saved",
    "fail_time",
)
# A gate's spot-check run and failure counts, as `gates` and `gate_summary` return them.
SPOT_CHECK_KEYS = ("spot_checks", "spot_check_failures")
# Only `gate_rows` returns it, so the dashboard's gates response keeps its shape.
LAST_FAILED_SPOT_CHECK = "last_failed_spot_check"

# Plain decimal text, optionally in the exponent form repr gives very large or small floats.
NUMBER_RE = re.compile(r"-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?")


@dataclass(frozen=True)
class Filters:
    """Restrict queries to a repo and a half-open time range.

    Attributes:
        repos: Git common directories to match; None selects the unknown repo.
            Empty means every repo.
        start: Inclusive lower bound as Unix seconds.
        end: Exclusive upper bound as Unix seconds.
        tz: IANA time zone name used to bucket days.
    """

    repos: tuple[str | None, ...] = ()
    start: float | None = None
    end: float | None = None
    tz: str = "UTC"


_UNKNOWN_REPO = "unknown repo"
# Skip scan: each step seeks the next distinct repo in the index instead of reading every event.
_DISTINCT_REPOS = """
WITH RECURSIVE r(repo) AS (
    SELECT MIN(repo) FROM events
    UNION ALL
    SELECT (SELECT MIN(repo) FROM events WHERE repo > r.repo) FROM r WHERE r.repo IS NOT NULL
)
SELECT repo FROM r WHERE repo IS NOT NULL
UNION ALL
SELECT NULL WHERE EXISTS (SELECT 1 FROM events WHERE repo IS NULL)
"""


def work_dir(repo: str) -> Path:
    """Return the folder that holds a repo's working copy, or the repo itself when bare."""
    path = Path(repo)
    return path.parent if path.name == ".git" else path


def _folder_name(repo: str | None) -> str:
    """Return a repo's folder name, which other repos may share."""
    return _UNKNOWN_REPO if repo is None else work_dir(repo).name


def _parent_labels(name: str, clashing: list[str], taken: set[str]) -> list[str]:
    """Return the shortest run of parent folders that tells apart repos sharing a name.

    A label must also differ from every name in `taken`, the folder names other repos show.
    Fall back to each full path when the parents cannot tell them apart.
    """
    folders = [work_dir(repo).parent for repo in clashing]
    parents = [[p for p in folder.parts if p != folder.anchor] for folder in folders]
    for depth in range(1, max(len(p) for p in parents) + 1):
        # A repo at the filesystem root has no parent folder to show, so it shows the root.
        labels = [f"{name} ({'/'.join(p[-depth:]) or '/'})" for p in parents]
        if len(set(labels)) == len(labels) and taken.isdisjoint(labels):
            return labels
    return clashing


def repo_names(repos: Iterable[str | None]) -> dict[str | None, str]:
    """Return a display name for each repo that no other repo in the set shares.

    Two clones in folders with the same name stay distinguishable in every view.

    Args:
        repos: Git common directories; None stands for events recorded without a repo.

    Returns:
        Each repo mapped to its folder name, with parent folders added when names clash.
    """
    unique = set(repos)
    names: dict[str | None, str] = {None: _UNKNOWN_REPO} if None in unique else {}
    by_name: dict[str, list[str]] = defaultdict(list)
    for repo in unique:
        if repo is not None:
            by_name[_folder_name(repo)].append(repo)
    taken = set(by_name) | set(names.values())
    for name, group in by_name.items():
        if len(group) == 1:
            names[group[0]] = name
        else:
            names.update(zip(group, _parent_labels(name, group, taken), strict=True))
    return names


class _RepoNames(dict[str | None, str]):
    """Repo display names that fall back to the folder name for a repo the lookup did not see."""

    def __missing__(self, repo: str | None) -> str:
        # Ingest can add a new repo between the name lookup and a later statement.
        return _folder_name(repo)


def all_repo_names(conn: sqlite3.Connection) -> _RepoNames:
    """Return repo_names over the whole archive, so a filter never changes a repo's name."""
    return _RepoNames(repo_names(repo for (repo,) in conn.execute(_DISTINCT_REPOS)))


def _zone(name: str) -> ZoneInfo:
    """Return the named time zone or raise ValueError."""
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError, OSError) as exc:
        msg = f"unknown time zone: {name!r}"
        raise ValueError(msg) from exc


def _where(
    filters: Filters,
    *,
    gate: str | None = None,
    exact_repo: tuple[str | None] | None = None,
) -> tuple[str, list[Any]]:
    """Build a WHERE clause from fixed fragments; every value binds as a parameter."""
    clauses: list[str] = [_KNOWN]
    params: list[Any] = []
    if exact_repo is not None:
        clauses.append("repo IS ?")
        params.append(exact_repo[0])
    elif filters.repos:
        known = [r for r in filters.repos if r is not None]
        parts: list[str] = []
        if known:
            parts.append(_in("repo", known))
            params.extend(known)
        if None in filters.repos:
            parts.append("repo IS NULL")
        clauses.append(f"({' OR '.join(parts)})")
    if gate is not None:
        clauses.append("gate = ?")
        params.append(gate)
    if filters.start is not None:
        clauses.append("ts >= ?")
        params.append(filters.start)
    if filters.end is not None:
        clauses.append("ts < ?")
        params.append(filters.end)
    return " WHERE " + " AND ".join(clauses), params


def _and(where: str, condition: str) -> str:
    """Append a condition to a WHERE clause from _where."""
    return f"{where} AND {condition}"


def _with_gates(
    where: str, params: list[Any], gates: Sequence[tuple[str | None, str]]
) -> tuple[str, list[Any]]:
    """Return `where` keeping only events of one of `gates`, as (repo, gate) pairs."""
    if not gates:
        return where, params
    clause = " OR ".join(["(repo IS ? AND gate = ?)"] * len(gates))
    return _and(where, f"({clause})"), [*params, *(value for gate in gates for value in gate)]


def _in(column: str, values: Sequence[object]) -> str:
    """Return `column IN (?, ...)` with one placeholder per value, for binding the values."""
    return f"{column} IN ({', '.join('?' * len(values))})"


def _skip_rate(skips: int, ran: int) -> float | None:
    """Return skips over ran, or None when nothing ran."""
    return skips / ran if ran else None


# Events that count toward flakiness. A failed spot check can mean a missing cache input, not a
# flaky test, so spot checks are left out of every flaky view.
_NOT_SPOT_CHECK = "spot_check = 0"
_FLAKY_EVENT = "tree IS NOT NULL AND " + _NOT_SPOT_CHECK
# A flaky tree: one gate's content that both failed and passed. Every flaky view groups by this.
# Grouped by the exact name, not the gate: two keys of one gate, such as two tool versions,
# that split a tree's outcomes are a real difference, not a flake.
_FLAKY_GROUP = (
    " GROUP BY repo, name, tree"
    " HAVING SUM(outcome = 'fail') > 0 AND SUM(outcome IN " + _GOOD + ") > 0"
)
_FAILED_SPOT_CHECK = "spot_check = 1 AND outcome = 'fail'"
# Keeps the counted events on the flaky trees in `ft`, from _flaky_trees_cte.
_ON_FLAKY_TREE = (
    _NOT_SPOT_CHECK + " AND EXISTS (SELECT 1 FROM ft WHERE ft.repo IS events.repo"  # noqa: S608
    " AND ft.name = events.name AND ft.tree = events.tree)"
)


def _flaky_trees_cte(where: str) -> str:
    """Return a WITH clause naming `ft`, the flaky trees among events matching `where`.

    The aggregate keeps SQLite from flattening the CTE, so it runs once rather than once per
    event that joins to it.
    """
    return (
        "WITH ft AS (SELECT repo, name, tree FROM events"  # noqa: S608
        + _and(where, _FLAKY_EVENT)
        + _FLAKY_GROUP
        + ") "
    )


def _flaky_trees(
    conn: sqlite3.Connection, where: str, params: list[Any]
) -> list[tuple[str | None, str, str, int, int, float]]:
    """Return (repo, gate, tree, fails, passes, last) for trees with a fail and a pass.

    A tree that is flaky under several keys of one gate comes back once, with their counts summed.
    """
    sql = (
        "SELECT repo, gate, tree, SUM(fails), SUM(passes), MAX(last) FROM ("  # noqa: S608
        "SELECT repo, gate, tree,"
        " SUM(outcome = 'fail') AS fails, SUM(outcome IN " + _GOOD + ") AS passes,"
        " MAX(ts) AS last"
        " FROM events"
        + _and(where, _FLAKY_EVENT)
        + _FLAKY_GROUP
        + ") GROUP BY repo, gate, tree ORDER BY MAX(last) DESC, tree"
    )
    return conn.execute(sql, params).fetchall()


def _event_row(raw: tuple[Any, ...], names: dict[str | None, str]) -> dict[str, Any]:
    """Convert a row selected with _ROW_COLUMNS into an API dict."""
    (
        ts,
        repo,
        name,
        outcome,
        duration,
        saved,
        exit_code,
        reason,
        tree,
        reported,
        gate,
        spot_check,
    ) = raw
    return {
        "ts": ts,
        "repo": repo,
        "repo_name": names[repo],
        "name": name,
        "gate": gate,
        "outcome": outcome,
        "duration": duration,
        "saved": saved,
        "exit_code": exit_code,
        "reason": reason,
        "tree": tree,
        "reported": bool(reported),
        "spot_check": bool(spot_check),
    }


def _totals(conn: sqlite3.Connection, filters: Filters) -> dict[str, Any]:
    """Return the headline totals and per-outcome counts for the filtered events."""
    where, params = _where(filters)
    row = conn.execute(
        "SELECT COUNT(*),"  # noqa: S608
        " COALESCE(SUM(outcome = 'skip'), 0),"
        " COALESCE(SUM(outcome IN " + _RAN + "), 0),"
        " COALESCE(SUM(outcome = 'uncached'), 0),"
        " COALESCE(SUM(outcome = 'fail'), 0),"
        " COALESCE(SUM(CASE WHEN outcome = 'skip' THEN saved END), 0.0),"
        " COALESCE(SUM(outcome = 'skip' AND saved IS NULL), 0),"
        " COALESCE(SUM(outcome = 'pass'), 0),"
        " COALESCE(SUM(outcome = 'pass_unrecorded'), 0),"
        " COALESCE(SUM(overhead), 0.0),"
        " COALESCE(SUM(waited), 0.0),"
        " COALESCE(SUM(duration), 0.0),"
        " COALESCE(SUM(CASE WHEN outcome = 'fail' THEN duration END), 0.0),"
        " COALESCE(SUM(spot_check), 0),"
        " COALESCE(SUM(spot_check AND outcome = 'fail'), 0),"
        # Distinct (repo, gate) pairs; char(0) keeps ('a', 'bc') apart from ('ab', 'c').
        " COUNT(DISTINCT CASE WHEN "
        + _FAILED_SPOT_CHECK
        + " THEN COALESCE(repo, '') || char(0) || gate END),"
        # Uncached runs never record overhead, so only runs that checked the cache count.
        " COALESCE(SUM(outcome IN " + _RAN + " AND (overhead IS NULL OR wait_known = 0)), 0)"
        " FROM events" + where,
        params,
    ).fetchone()
    (
        runs,
        skips,
        ran,
        uncached,
        failures,
        saved,
        unknown,
        passes,
        unrecorded,
        overhead,
        waited,
        time_spent,
        fail_time,
        spot_runs,
        spot_failed,
        spot_failed_gates,
        cost_unknown,
    ) = row
    flaky_gates = len({(r[0], r[1]) for r in _flaky_trees(conn, where, params)})
    return {
        "time_saved": float(saved),
        "unknown_saved_skips": unknown,
        "overhead": float(overhead),
        "waited": float(waited),
        "time_spent": float(time_spent),
        "fail_time": float(fail_time),
        "cost_unknown_runs": cost_unknown,
        "runs": runs,
        "skips": skips,
        "skip_rate": _skip_rate(skips, ran),
        "uncached": uncached,
        "failures": failures,
        "spot_checks": spot_runs,
        "spot_check_failures": spot_failed,
        "flaky_gates": flaky_gates,
        # One triage row per gate and reason, as `triage` lists them.
        "triage_items": flaky_gates + spot_failed_gates,
        "outcomes": {
            "skip": skips,
            "pass": passes,
            "pass_unrecorded": unrecorded,
            "fail": failures,
            "uncached": uncached,
        },
    }


@dataclass
class _Tally:
    """Run counts and seconds summed over some events.

    `ran` counts the runs that checked the cache, the skip rate's denominator.
    """

    runs: int = 0
    saved: float = 0.0
    failures: int = 0
    spent: float = 0.0
    skips: int = 0
    ran: int = 0
    spot_checks: int = 0
    spot_check_failures: int = 0

    def add(self, other: _Tally) -> None:
        """Add another tally's counts to this one."""
        for f in fields(self):
            setattr(self, f.name, getattr(self, f.name) + getattr(other, f.name))


def _bucket_start(bucket_id: int, zone: ZoneInfo) -> datetime:
    """Return the local start of a quarter-hour bucket."""
    return datetime.fromtimestamp(bucket_id * _BUCKET_SECONDS, tz=UTC).astimezone(zone)


def _local_buckets(
    conn: sqlite3.Connection, filters: Filters
) -> Iterator[tuple[int, datetime, _Tally]]:
    """Yield the id, local start, and tally of each quarter-hour bucket that holds an event.

    Raises:
        ValueError: If the filter's time zone is unknown.
    """
    zone = _zone(filters.tz)
    where, params = _where(filters)
    for (
        bucket_id,
        saved,
        failures,
        runs,
        spent,
        skips,
        ran,
        spot_checks,
        spot_check_failures,
    ) in conn.execute(
        "SELECT " + _BUCKET + ","  # noqa: S608
        " COALESCE(SUM(CASE WHEN outcome = 'skip' THEN saved END), 0.0),"
        " SUM(outcome = 'fail'), COUNT(*),"
        " COALESCE(SUM(duration), 0.0),"
        " SUM(outcome = 'skip'),"
        " SUM(outcome IN " + _RAN + "),"
        " SUM(spot_check), SUM(spot_check AND outcome = 'fail')"
        " FROM events" + where + " GROUP BY 1",
        params,
    ):
        start = _bucket_start(bucket_id, zone)
        yield (
            bucket_id,
            start,
            _Tally(
                runs=int(runs),
                saved=float(saved),
                failures=int(failures),
                spent=float(spent),
                skips=int(skips),
                ran=int(ran),
                spot_checks=int(spot_checks),
                spot_check_failures=int(spot_check_failures),
            ),
        )


def previous_window(conn: sqlite3.Connection, filters: Filters, *, now: float) -> Filters | None:
    """Return the window of equal length that ends where the filtered range starts.

    Args:
        conn: Archive connection.
        filters: The current range; its end defaults to now.
        now: Current Unix time in seconds.

    Returns:
        The previous window, or None when the range has no start, the window starts beyond
        retention, or it starts before the archive's first event in any repo.
    """
    if filters.start is None:
        return None
    end = filters.end if filters.end is not None else now
    length = end - filters.start
    previous_start = filters.start - length
    if length <= 0 or previous_start < now - RETENTION_DAYS * 86400:
        return None
    earliest = conn.execute("SELECT MIN(ts) FROM events WHERE " + _KNOWN).fetchone()[0]  # noqa: S608
    if earliest is None or previous_start < earliest:
        return None
    return Filters(repos=filters.repos, start=previous_start, end=filters.start, tz=filters.tz)


def summary(
    conn: sqlite3.Connection, filters: Filters, *, now: float | None = None
) -> dict[str, Any]:
    """Return headline totals, outcome counts, previous-period totals, and per-day buckets.

    Args:
        conn: Archive connection.
        filters: Repo and range filters.
        now: Current Unix time in seconds; defaults to the clock.

    Returns:
        Totals, with runs counting every recorded event including uncached ones, plus a
        previous-period block that is None when no comparable window exists.
    """
    result = _totals(conn, filters)
    window = previous_window(conn, filters, now=time.time() if now is None else now)
    previous: dict[str, Any] | None = None
    if window is not None and window.start is not None and window.end is not None:
        totals = _totals(conn, window)
        previous = {
            key: totals[key]
            for key in (
                "time_saved",
                "time_spent",
                "runs",
                "skips",
                "skip_rate",
                "failures",
                "flaky_gates",
                "spot_check_failures",
            )
        }
        previous["days"] = (window.end - window.start) / 86400
    days: dict[str, _Tally] = defaultdict(_Tally)
    for _, start, tally in _local_buckets(conn, filters):
        days[start.date().isoformat()].add(tally)
    return {
        **result,
        "previous": previous,
        "daily": [{"day": day, **asdict(t)} for day, t in sorted(days.items())],
    }


_WAIT_COLUMNS = (
    "COUNT(waited),"
    " COALESCE(SUM(waited IS NOT NULL AND outcome = 'skip'), 0),"
    " COALESCE(SUM(waited IS NOT NULL AND reported), 0),"
    " COALESCE(SUM(waited IS NOT NULL AND wait_timed_out), 0),"
    " COALESCE(SUM(waited), 0.0),"
    # Each wait, for the median, collected in the same pass over the range.
    " json_group_array(waited) FILTER (WHERE waited IS NOT NULL)"
)
# A run that waited can still end uncached when its new snapshot has no tree key.
_CHECKED_COLUMNS = (
    "COALESCE(SUM(outcome IN " + _RAN + " OR waited IS NOT NULL), 0),"
    " COALESCE(SUM(outcome IN " + _RAN + " AND wait_known = 0), 0),"
    " COALESCE(SUM(CASE WHEN waited IS NOT NULL AND outcome = 'skip' THEN saved END), 0.0)"
)


def _wait_counts(
    waited: int, skipped: int, reported: int, timed_out: int, total_wait: float, waits_json: str
) -> dict[str, Any]:
    """Convert the values selected with _WAIT_COLUMNS into wait counts."""
    waits = json.loads(waits_json)
    return {
        "waited": waited,
        "skipped": skipped,
        "reported": reported,
        "ran": waited - skipped - reported,
        "timed_out": timed_out,
        "total_wait": float(total_wait),
        "median_wait": float(statistics.median(waits)) if waits else None,
    }


def coalescing(conn: sqlite3.Connection, filters: Filters) -> dict[str, Any]:
    """Return how often runs waited for a concurrent run of the same gate, and how it ended.

    A run that waited then skipped on the pass of the run it waited for, reported that
    run's failure without running, or ran the command itself: after a failed or
    interrupted run, after its key changed during the wait, or after the wait timed out.

    Args:
        conn: Archive connection.
        filters: Repo and range filters.

    Returns:
        Counts of runs that waited and of each ending, the total and median wait in
        seconds, the seconds saved by the skips after a wait, and how many runs that checked
        the cache came from a gate-cache that did not record waits.
    """
    where, params = _where(filters)
    checked, unknown, saved, *waits = conn.execute(
        f"SELECT {_CHECKED_COLUMNS}, {_WAIT_COLUMNS} FROM events{where}",  # noqa: S608
        params,
    ).fetchone()
    return {
        "runs": checked,
        "unknown_runs": unknown,
        **_wait_counts(*waits),
        "saved": float(saved),
    }


GateKey = tuple[str | None, str]


def _gate_where(filters: Filters, gate_key: GateKey | None) -> tuple[str, list[Any]]:
    """Build the WHERE clause of a per-gate query, scoped to one gate's repo and name when given."""
    if gate_key is None:
        return _where(filters)
    repo, name = gate_key
    return _where(filters, gate=name, exact_repo=(repo,))


def gate_waits(
    conn: sqlite3.Connection, filters: Filters, *, gate_key: GateKey | None = None
) -> dict[GateKey, dict[str, Any]]:
    """Return the wait counts of coalescing() for each gate that waited, without the run totals.

    Args:
        conn: Archive connection.
        filters: Repo and range filters.
        gate_key: One gate's (repo, name) to scan alone; None covers every gate in `filters`.
    """
    where, params = _gate_where(filters, gate_key)
    rows = conn.execute(
        f"SELECT repo, gate, {_WAIT_COLUMNS} FROM events{where} GROUP BY repo, gate",  # noqa: S608
        params,
    )
    return {(repo, gate): _wait_counts(*waits) for repo, gate, *waits in rows if waits[0] > 0}


def hourly(conn: sqlite3.Connection, filters: Filters) -> dict[str, Any]:
    """Return activity for each hour of the week in the filter's time zone.

    Args:
        conn: Archive connection.
        filters: Repo and range filters.

    Returns:
        168 cells ordered by weekday then hour, with weekday 0 as Sunday.
    """
    grid: dict[tuple[int, int], _Tally] = defaultdict(_Tally)
    for _, start, tally in _local_buckets(conn, filters):
        grid[(start.isoweekday() % 7, start.hour)].add(tally)
    cells: list[dict[str, Any]] = []
    for weekday in range(7):
        for hour in range(24):
            cell = grid.get((weekday, hour), _Tally())
            cells.append(
                {
                    "weekday": weekday,
                    "hour": hour,
                    "runs": cell.runs,
                    "saved": cell.saved,
                    "failures": cell.failures,
                }
            )
    return {"cells": cells}


def gates(conn: sqlite3.Connection, filters: Filters) -> dict[str, Any]:
    """Return per-gate metrics ordered by time saved."""
    return {
        "gates": [
            {key: value for key, value in row.items() if key != LAST_FAILED_SPOT_CHECK}
            for row in gate_rows(conn, filters)
        ]
    }


def gate_rows(conn: sqlite3.Connection, filters: Filters) -> list[dict[str, Any]]:
    """Return the metrics of `gates`, plus each gate's newest failed spot check."""
    where, params = _where(filters)
    out = _gate_rows(conn, where, params)
    out.sort(key=lambda g: (-g["time_saved"], g["repo_name"], g["name"]))
    return out


def _gate_rows(conn: sqlite3.Connection, where: str, params: list[Any]) -> list[dict[str, Any]]:
    """Return the metrics of each gate with events matching `where`, in no set order."""
    names = all_repo_names(conn)
    flaky_keys = {(r[0], r[1]) for r in _flaky_trees(conn, where, params)}
    durations = _pass_durations(conn, where, params)
    resources = _resource_costs(conn, where, params)
    rows = conn.execute(
        "SELECT repo, gate, COUNT(*),"  # noqa: S608
        " SUM(outcome = 'skip'), SUM(outcome IN " + _RAN + "),"
        " COALESCE(SUM(CASE WHEN outcome = 'skip' THEN saved END), 0.0),"
        " SUM(outcome = 'fail'), MAX(ts), COALESCE(SUM(duration), 0.0),"
        " COALESCE(SUM(CASE WHEN outcome = 'fail' THEN duration END), 0.0),"
        " COALESCE(SUM(spot_check), 0), COALESCE(SUM(spot_check AND outcome = 'fail'), 0),"
        " MAX(CASE WHEN " + _FAILED_SPOT_CHECK + " THEN ts END)"
        " FROM events" + where + " GROUP BY repo, gate",
        params,
    ).fetchall()
    out: list[dict[str, Any]] = []
    for (
        repo,
        gate,
        runs,
        skips,
        ran,
        saved,
        failures,
        last,
        spent,
        fail_time,
        spot_checks,
        spot_check_failures,
        last_failed_spot_check,
    ) in rows:
        durs = durations.get((repo, gate), [])
        avg_run, median_run = _run_stats(durs)
        cpu_ratio, peak_rss, rss_values = resources.get((repo, gate), (None, None, []))
        out.append(
            {
                "repo": repo,
                "repo_name": names[repo],
                "name": gate,
                "runs": runs,
                "skips": skips,
                "skip_rate": _skip_rate(skips, ran),
                "avg_run": avg_run,
                "median_run": median_run,
                "time_saved": float(saved),
                "failures": failures,
                "spot_checks": spot_checks,
                "spot_check_failures": spot_check_failures,
                LAST_FAILED_SPOT_CHECK: last_failed_spot_check,
                "last_run": last,
                "flaky": (repo, gate) in flaky_keys,
                "time_spent": float(spent),
                "fail_time": float(fail_time),
                "p90_run": _p90(durs),
                "cpu_ratio": cpu_ratio,
                "peak_rss": peak_rss,
                "median_rss": float(statistics.median(rss_values)) if rss_values else None,
            }
        )
    return out


SpentStatus = Literal["all", "passing", "failing"]
_SPENT_CONDITIONS: dict[str, str] = {
    "all": "duration IS NOT NULL",
    "passing": "duration IS NOT NULL AND outcome != 'fail'",
    "failing": "duration IS NOT NULL AND outcome = 'fail'",
}


def spent(conn: sqlite3.Connection, filters: Filters, *, status: SpentStatus) -> dict[str, Any]:
    """Return daily run time for the top gates by time spent, with the rest as "other".

    Args:
        conn: Archive connection.
        filters: Repo, range, and time zone filters.
        status: Which runs count: all, passing, or failing.

    Returns:
        The status, the top gates with their totals, and per-day seconds in the same order
        as the gates. Days with no time are left out.

    Raises:
        ValueError: If the status or the filter's time zone is unknown.
    """
    if status not in _SPENT_CONDITIONS:
        msg = f"status must be one of {', '.join(_SPENT_CONDITIONS)}"
        raise ValueError(msg)
    zone = _zone(filters.tz)
    where, params = _where(filters)
    where = _and(where, _SPENT_CONDITIONS[status])
    names = all_repo_names(conn)
    totals: dict[tuple[str | None, str], float] = defaultdict(float)
    cells: dict[str, dict[tuple[str | None, str], float]] = defaultdict(lambda: defaultdict(float))
    days: dict[int, str] = {}
    for repo, gate, bucket_id, seconds in conn.execute(
        "SELECT repo, gate, " + _BUCKET + ", SUM(duration)"  # noqa: S608
        " FROM events" + where + " GROUP BY repo, gate, 3",
        params,
    ):
        key = (repo, gate)
        totals[key] += float(seconds)
        if bucket_id not in days:
            days[bucket_id] = _bucket_start(bucket_id, zone).date().isoformat()
        cells[days[bucket_id]][key] += float(seconds)
    top = sorted(totals, key=lambda k: (-totals[k], k[1], names[k[0]]))[:_TOP_SPENT]
    top_keys = set(top)
    multi_repo = len({repo for repo, _ in top}) > 1
    daily = []
    for day, by_gate in sorted(cells.items()):
        per_gate = [by_gate.get(key, 0.0) for key in top]
        other = sum(seconds for key, seconds in by_gate.items() if key not in top_keys)
        daily.append({"day": day, "gates": per_gate, "other": other})
    return {
        "status": status,
        "gates": [
            {
                "repo": repo,
                "repo_name": names[repo],
                "name": gate,
                "label": f"{gate} · {names[repo]}" if multi_repo else gate,
                "total": totals[(repo, gate)],
            }
            for repo, gate in top
        ],
        "daily": daily,
    }


def _run_stats(durations: list[float]) -> tuple[float | None, float | None]:
    """Return the average and median of passing durations, None for both when there are none."""
    if not durations:
        return None, None
    return statistics.fmean(durations), float(statistics.median(durations))


def _p90(values: list[float]) -> float | None:
    """Return the 90th percentile, or None when there are too few values."""
    if len(values) < _MIN_SPREAD_RUNS:
        return None
    return statistics.quantiles(values, n=10, method="inclusive")[8]


def _pass_durations(
    conn: sqlite3.Connection, where: str, params: list[Any]
) -> dict[tuple[str | None, str], list[float]]:
    """Return the passing durations of each gate."""
    durations: dict[tuple[str | None, str], list[float]] = defaultdict(list)
    for repo, gate, duration in conn.execute(
        "SELECT repo, gate, duration FROM events"  # noqa: S608
        + _and(where, "outcome = 'pass' AND duration IS NOT NULL"),
        params,
    ):
        durations[(repo, gate)].append(duration)
    return durations


def _histogram(passes: list[float], median: float | None) -> dict[str, Any] | None:
    """Bin passing durations linearly from the fastest to the slowest, None with too few passes."""
    if len(passes) < _MIN_SPREAD_RUNS:
        return None
    low, high = min(passes), max(passes)
    if high == low:
        high = low + 1
    width = (high - low) / _HISTOGRAM_BINS
    counts = [0] * _HISTOGRAM_BINS
    for duration in passes:
        counts[min(int((duration - low) / width), _HISTOGRAM_BINS - 1)] += 1
    return {
        "edges": [*(low + i * width for i in range(_HISTOGRAM_BINS)), high],
        "counts": counts,
        "median": median,
        "p90": _p90(passes),
    }


def _failure_timing(
    conn: sqlite3.Connection, where: str, params: list[Any], median: float | None
) -> dict[str, Any]:
    """Split the time failed runs took into early and late against the median pass."""
    threshold = median * _EARLY_FAIL_FRACTION if median is not None else None
    buckets = {key: {"runs": 0, "time": 0.0} for key in ("early", "late", "unclassified")}
    for (duration,) in conn.execute(
        "SELECT duration FROM events"  # noqa: S608
        + _and(where, "outcome = 'fail' AND duration IS NOT NULL"),
        params,
    ):
        key = "unclassified"
        if threshold is not None:
            key = "early" if duration < threshold else "late"
        buckets[key]["runs"] += 1
        buckets[key]["time"] += duration
    return {"threshold": threshold, **buckets}


@dataclass
class _ResourceTotals:
    """Running CPU, wall time, and memory samples of one gate."""

    cpu: float = 0.0
    wall: float = 0.0
    has_cpu: bool = False
    rss: list[int] = field(default_factory=list)


def _is_number(value: object) -> bool:
    """Return whether a value read from the raw line is a real number, not a boolean."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _resource_costs(
    conn: sqlite3.Connection, where: str, params: list[Any]
) -> dict[tuple[str | None, str], tuple[float | None, int | None, list[int]]]:
    """Return CPU seconds per wall second, peak memory, and memory samples for each gate."""
    totals: dict[tuple[str | None, str], _ResourceTotals] = defaultdict(_ResourceTotals)
    for repo, gate, duration, cpu, rss in conn.execute(
        "SELECT repo, gate, duration,"  # noqa: S608
        " CASE WHEN json_valid(raw) THEN json_extract(raw, '$.cpu') END,"
        " CASE WHEN json_valid(raw) THEN json_extract(raw, '$.max_rss') END"
        # Only runs that ran the command record usage, so skips need no JSON parsing.
        " FROM events" + _and(where, "duration IS NOT NULL"),
        params,
    ):
        usage = totals[(repo, gate)]
        if _is_number(cpu):
            usage.cpu += cpu
            usage.wall += duration
            usage.has_cpu = True
        if _is_number(rss):
            usage.rss.append(int(rss))
    return {
        key: (
            usage.cpu / usage.wall if usage.has_cpu and usage.wall else None,
            max(usage.rss) if usage.rss else None,
            usage.rss,
        )
        for key, usage in totals.items()
    }


def _median_passes(
    conn: sqlite3.Connection, filters: Filters
) -> dict[tuple[str | None, str], tuple[float, int]]:
    """Return the median passing duration and pass count for each gate."""
    where, params = _where(filters)
    durations = _pass_durations(conn, where, params)
    return {key: (float(statistics.median(d)), len(d)) for key, d in durations.items()}


def slowdowns(
    conn: sqlite3.Connection,
    filters: Filters,
    *,
    now: float | None = None,
    min_runs: int = 5,
    limit: int = 5,
) -> dict[str, Any]:
    """Return the gates whose median passing run time grew since the previous window.

    Args:
        conn: Archive connection.
        filters: Repo and range filters; the range is the current window.
        now: Current Unix time in seconds; defaults to the clock.
        min_runs: Passing runs a gate needs in each window to be compared.
        limit: Most gates to return.

    Returns:
        Gates sorted by relative growth, and whether a previous window exists.
    """
    current_time = time.time() if now is None else now
    window = previous_window(conn, filters, now=current_time)
    if window is None:
        return {"gates": [], "comparable": False}
    names = all_repo_names(conn)
    current = replace(filters, end=filters.end if filters.end is not None else current_time)
    before = _median_passes(conn, window)
    after = _median_passes(conn, current)
    out: list[dict[str, Any]] = []
    for (repo, gate), (median_now, runs_now) in after.items():
        median_before, runs_before = before.get((repo, gate), (0.0, 0))
        if (
            min(runs_now, runs_before) < min_runs
            or median_before <= 0
            or median_now <= median_before
        ):
            continue
        out.append(
            {
                "repo": repo,
                "repo_name": names[repo],
                "name": gate,
                "before": median_before,
                "now": median_now,
                "change": median_now / median_before - 1,
            }
        )
    out.sort(key=lambda g: (-g["change"], g["repo_name"], g["name"]))
    return {"gates": out[:limit], "comparable": True}


def _slowest_tests(
    conn: sqlite3.Connection,
    where: str,
    params: list[Any],
    *,
    gate_median: float | None,
    since: float,
    limit: int | None = SLOWEST_TESTS_LIMIT,
) -> list[dict[str, Any]]:
    """Return the tests with the longest median passing duration in the gate's recent runs.

    A `limit` of None returns every test.
    """
    # The median averages the middle row, or the middle two, of each test's sorted durations.
    rows = conn.execute(
        "WITH runs AS (SELECT id FROM events"  # noqa: S608
        + _and(
            where,
            "ts >= ? AND EXISTS (SELECT 1 FROM test_results WHERE event_id = events.id)",
        )
        + " ORDER BY ts DESC LIMIT ?),"
        " ranked AS (SELECT tests.name AS name, test_results.duration AS duration,"
        " ROW_NUMBER() OVER (PARTITION BY tests.name ORDER BY test_results.duration) AS rank,"
        " COUNT(*) OVER (PARTITION BY tests.name) AS runs"
        " FROM runs"
        " JOIN test_results ON test_results.event_id = runs.id"
        " JOIN tests ON tests.id = test_results.test_id"
        " WHERE test_results.outcome IN " + _TEST_PASSED + " AND test_results.duration IS NOT NULL)"
        " SELECT name, AVG(duration) AS median, MAX(runs) FROM ranked"
        " WHERE rank IN ((runs + 1) / 2, (runs + 2) / 2)"
        " GROUP BY name ORDER BY median DESC, name LIMIT ?",
        [*params, since, SLOWEST_TESTS_RUNS, -1 if limit is None else limit],
    ).fetchall()
    return [
        {
            "name": test,
            "median": median,
            "runs": runs,
            "share": median / gate_median if gate_median else None,
        }
        for test, median, runs in rows
    ]


def _report_problem_counts(
    conn: sqlite3.Connection, where: str, params: list[Any]
) -> dict[GateKey, dict[str, int]]:
    """Count, per gate, the recent runs whose test reports were missing, stale, or invalid.

    A run counts once, under the status of its unread reports. That is `junit` when no report
    was read, else `junit_problem`. Only gates with a problem appear.
    """
    out: dict[GateKey, dict[str, int]] = {}
    # Ranks on the index alone, so the JSON is read only for the runs that count.
    for repo, gate, status in conn.execute(
        "SELECT r.repo, r.gate,"  # noqa: S608
        " CASE WHEN json_valid(e.raw) THEN CASE json_type(e.raw, '$.junit')"
        " WHEN 'text' THEN json_extract(e.raw, '$.junit')"
        " ELSE json_extract(e.raw, '$.junit_problem') END END"
        " FROM (SELECT id, repo, gate,"
        " ROW_NUMBER() OVER (PARTITION BY repo, gate ORDER BY ts DESC, id DESC) AS rn"
        " FROM events" + _and(where, "outcome != 'skip' AND NOT reported") + ") AS r"
        " JOIN events AS e ON e.id = r.id WHERE r.rn <= ?",
        [*params, REPORT_PROBLEM_RUNS],
    ):
        if status in _REPORT_PROBLEMS:
            counts = out.setdefault((repo, gate), dict.fromkeys(_REPORT_PROBLEMS, 0))
            counts[status] += 1
    return out


def _tests_cutoff(filters: Filters, since: float) -> float | None:
    """Return where per-test retention starts when the window reaches further back."""
    # A rolling range as long as the retention starts a little before `since`, because the
    # browser computed its start before this request reached the server.
    reaches = filters.start is None or filters.start < since - _TESTS_CUTOFF_SLACK
    return since if reaches else None


def gate_detail(
    conn: sqlite3.Connection,
    filters: Filters,
    *,
    repo: str | None,
    name: str,
    now: float | None = None,
) -> dict[str, Any]:
    """Return the pass trend, recent events, flaky trees, and per-test detail of one gate.

    Args:
        conn: Archive connection.
        filters: Range filters; its repo is ignored.
        repo: The gate's repo; None selects events recorded without a repo.
        name: Gate, as stats group it: the name before any `@` key.
        now: Current Unix time in seconds; defaults to the clock.

    Returns:
        The detail body.
    """
    where, params = _where(filters, gate=name, exact_repo=(repo,))
    names = all_repo_names(conn)
    since = tests_since(time.time() if now is None else now)
    has_tests = _has_tests(conn, repo=repo, name=name)
    trend = conn.execute(
        "SELECT ts, duration FROM events"  # noqa: S608
        + _and(where, "outcome = 'pass' AND duration IS NOT NULL")
        + " ORDER BY ts",
        params,
    ).fetchall()
    recent = conn.execute(
        f"SELECT {_ROW_COLUMNS} FROM events{where} ORDER BY ts DESC, id DESC LIMIT ?",  # noqa: S608
        [*params, _RECENT_LIMIT],
    ).fetchall()
    pass_durations = [d for _, d in trend]
    median = statistics.median(pass_durations) if pass_durations else None
    by_source = sorted(
        _breakdown_rows(conn, where, params, "source", names),
        key=lambda r: (-r["time_spent"], r["label"]),
    )
    return {
        "repo": repo,
        "repo_name": names[repo],
        "name": name,
        "histogram": _histogram(pass_durations, median),
        "failure_timing": _failure_timing(conn, where, params, median),
        "by_source": [
            {k: row[k] for k in ("key", "label", "title", "runs", "time_spent")}
            for row in by_source
            if row["time_spent"] > 0
        ],
        "trend": [{"ts": ts, "duration": d} for ts, d in trend],
        "recent": [_event_row(r, names) for r in recent],
        "flaky_trees": gate_flaky_trees(conn, filters, repo=repo, name=name),
        "slowest_tests": (
            _slowest_tests(conn, where, params, gate_median=median, since=since)
            if has_tests
            else []
        ),
        "has_tests": has_tests,
        "report_problems": _report_problem_counts(conn, where, params).get(
            (repo, name), dict.fromkeys(_REPORT_PROBLEMS, 0)
        ),
        "tests_cutoff": _tests_cutoff(filters, since),
    }


def gate_flaky_trees(
    conn: sqlite3.Connection, filters: Filters, *, repo: str | None, name: str
) -> list[dict[str, Any]]:
    """Return the trees on which the gate both failed and passed, newest first."""
    where, params = _where(filters, gate=name, exact_repo=(repo,))
    return [
        {"tree": tree, "fails": fails, "passes": passes, "last": last}
        for _, _, tree, fails, passes, last in _flaky_trees(conn, where, params)
    ]


def gate_failure_timing(
    conn: sqlite3.Connection, filters: Filters, *, repo: str | None, name: str
) -> dict[str, Any]:
    """Return how the gate's failed runs split into early and late against its median pass."""
    where, params = _where(filters, gate=name, exact_repo=(repo,))
    passes = _pass_durations(conn, where, params).get((repo, name), [])
    median = statistics.median(passes) if passes else None
    return _failure_timing(conn, where, params, median)


def repos(conn: sqlite3.Connection, filters: Filters) -> dict[str, Any]:
    """Return per-repo rollups ordered by time saved."""
    return {
        "repos": [
            {
                "repo": row["repo"],
                "repo_name": row["label"],
                **{k: row[k] for k in ("runs", "skip_rate", "time_saved", "failures", "gates")},
            }
            for row in breakdown(conn, filters, by="repo")["rows"]
        ]
    }


def _raw_text(field: str) -> str:
    """Return SQL for one field of the raw line as text, NULL when the line or field is absent."""
    # Read at query time rather than promoted to columns: the breakdown groups every row in
    # the range, so a column index would go unused, and no migration rewrites the archive.
    return f"CASE WHEN json_valid(raw) THEN CAST(json_extract(raw, '$.{field}') AS TEXT) END"


_TRIGGER = _raw_text("trigger")
TRIGGER_LABELS = {
    "agent": "Agent",
    "hook": "Git hook",
    "ci": "CI",
    "terminal": "Terminal",
    "other": "Other",
}
_MACHINE_PREFIX = 8


@dataclass(frozen=True)
class _Label:
    """How one breakdown row reads: its name, hover text, and whether it holds runs with no value."""

    label: str
    title: str | None = None
    missing: bool = False
    gate: str | None = None


# One group's key values and its `extra` value, which is SQL from the newest run in the group.
_Group = tuple[tuple[str | None, ...], str | None]


def _repo_labels(groups: list[_Group], names: _RepoNames) -> list[_Label]:
    return [_Label(names[g[0]], title=g[0], missing=g[0] is None) for g, _ in groups]


def _gate_labels(groups: list[_Group], _names: _RepoNames) -> list[_Label]:
    return [_Label(str(g[1]), title=g[0], gate=g[1]) for g, _ in groups]


def _source_labels(groups: list[_Group], _names: _RepoNames) -> list[_Label]:
    def one(trigger: str | None, agent: str | None) -> _Label:
        if trigger is None:
            return _Label(
                "No source recorded",
                title="Runs that recorded no source, such as runs from older gate-cache versions",
                missing=True,
            )
        if trigger == "agent" and agent:
            return _Label(f"Agent: {agent}")
        return _Label(TRIGGER_LABELS.get(trigger, trigger))

    return [one(g[0], g[1]) for g, _ in groups]


def _branch_labels(groups: list[_Group], _names: _RepoNames) -> list[_Label]:
    missing = _Label(
        "No branch recorded",
        title="Runs on a detached HEAD, or runs from older gate-cache versions",
        missing=True,
    )
    return [missing if g[1] is None else _Label(g[1], title=g[0]) for g, _ in groups]


def _machine_labels(groups: list[_Group], _names: _RepoNames) -> list[_Label]:
    """Label machines by their latest host name, adding an ID prefix where two share one."""
    base = [
        None if m is None else host or f"Machine {m[:_MACHINE_PREFIX]}" for (m,), host in groups
    ]
    counts = Counter(base)
    out: list[_Label] = []
    for ((machine,), _), label in zip(groups, base, strict=True):
        if machine is None or label is None:
            out.append(
                _Label(
                    "No machine recorded",
                    title="Runs that recorded no machine, such as runs from older gate-cache versions",
                    missing=True,
                )
            )
        else:
            shared = counts[label] > 1
            out.append(
                _Label(f"{label} ({machine[:_MACHINE_PREFIX]})" if shared else label, title=machine)
            )
    return out


@dataclass(frozen=True)
class _Grouping:
    """How the breakdown groups and names runs for one dimension.

    Attributes:
        columns: SQL for the group key, each value a column or a raw-line field.
        labels: Names every row at once, so a label can depend on the other rows.
        in_repo: Whether `columns[0]` is the repo. Rows keyed by more than the repo add
            the repo name to their label when they come from several repos.
        extra: SQL whose value from each group's newest run reaches `labels`.
    """

    columns: tuple[str, ...]
    labels: Callable[[list[_Group], _RepoNames], list[_Label]]
    in_repo: bool = False
    extra: str | None = None


# One entry here adds a grouping; the dashboard lists its choices in frontend/src/lib/dimensions.ts.
_GROUPINGS: dict[str, _Grouping] = {
    "repo": _Grouping(("repo",), _repo_labels, in_repo=True),
    "gate": _Grouping(("repo", "gate"), _gate_labels, in_repo=True),
    "source": _Grouping(
        (_TRIGGER, f"CASE WHEN {_TRIGGER} = 'agent' THEN NULLIF({_raw_text('agent')}, '') END"),
        _source_labels,
    ),
    "branch": _Grouping(("repo", _raw_text("branch")), _branch_labels, in_repo=True),
    "machine": _Grouping((_raw_text("machine"),), _machine_labels, extra=_raw_text("host")),
}
DIMENSIONS: tuple[str, ...] = tuple(_GROUPINGS)


def _grouping(by: str) -> _Grouping:
    """Return a dimension's grouping or raise ValueError."""
    try:
        return _GROUPINGS[by]
    except KeyError:
        msg = f"unknown breakdown: {by!r}; expected one of {', '.join(DIMENSIONS)}"
        raise ValueError(msg) from None


def group_filter(by: str, key: str) -> tuple[str, list[str | None]]:
    """Return a WHERE condition and its parameters that select one breakdown row's runs.

    Args:
        by: The dimension the key came from.
        key: A row's opaque `key` from `breakdown`.

    Returns:
        The condition, to append with AND, and the values it binds.

    Raises:
        ValueError: If the dimension is unknown or the key does not fit it.
    """
    columns = _grouping(by).columns
    try:
        values = json.loads(key)
    except (ValueError, RecursionError):
        values = None
    if not (
        isinstance(values, list)
        and len(values) == len(columns)
        and all(v is None or isinstance(v, str) for v in values)
    ):
        msg = f"malformed {by} key: {key!r}"
        raise ValueError(msg)
    condition = " AND ".join(f"({column}) IS ?" for column in columns)
    return f"({condition})", values


def _breakdown_rows(
    conn: sqlite3.Connection,
    where: str,
    params: list[Any],
    by: str,
    names: _RepoNames | None = None,
) -> list[dict[str, Any]]:
    """Return per-group rollups of the events a WHERE clause selects, ordered by time saved.

    Gate rows also carry the average and median passing duration, taken from the same events.

    Args:
        conn: Archive connection.
        where: A WHERE clause, as `_where` builds it.
        params: The values the clause binds.
        by: The dimension to group by, one of DIMENSIONS.
        names: Repo display names; loaded from the archive when omitted.

    Returns:
        The rows, each with an opaque `key`.
    """
    grouping = _grouping(by)
    width = len(grouping.columns)
    names = all_repo_names(conn) if names is None else names
    # With exactly one MAX aggregate, SQLite takes the bare `extra` value from that newest row.
    rows = conn.execute(
        "SELECT " + ", ".join(grouping.columns) + ","  # noqa: S608
        f" {grouping.extra or 'NULL'}, MAX(ts),"
        " COUNT(*), SUM(outcome = 'skip'), SUM(outcome IN " + _RAN + "),"
        " COALESCE(SUM(CASE WHEN outcome = 'skip' THEN saved END), 0.0),"
        " SUM(outcome = 'fail'), COUNT(DISTINCT json_array(repo, gate)),"
        " COALESCE(SUM(duration), 0.0)"
        " FROM events" + where + " GROUP BY " + ", ".join(str(i) for i in range(1, width + 1)),
        params,
    ).fetchall()
    labels = grouping.labels([(tuple(row[:width]), row[width]) for row in rows], names)
    durations = _pass_durations(conn, where, params) if by == "gate" else {}
    # Gate and branch names repeat across repos, so they name the repo only when rows mix repos.
    with_repo = grouping.in_repo and width > 1 and len({row[0] for row in rows}) > 1
    out: list[dict[str, Any]] = []
    for row, label in zip(rows, labels, strict=True):
        group = row[:width]
        runs, skips, ran, saved, failures, n_gates, spent = row[width + 2 :]
        repo = group[0] if grouping.in_repo else None
        avg_run, median_run = (
            _run_stats(durations.get((group[0], group[1]), [])) if by == "gate" else (None, None)
        )
        out.append(
            {
                "key": json.dumps(list(group)),
                "label": f"{label.label} · {names[repo]}" if with_repo else label.label,
                "title": label.title,
                "missing": label.missing,
                "repo": repo,
                "name": label.gate,
                "runs": runs,
                "skip_rate": _skip_rate(skips, ran),
                "time_saved": float(saved),
                "time_spent": float(spent),
                "avg_run": avg_run,
                "median_run": median_run,
                "failures": failures,
                "gates": n_gates,
            }
        )
    out.sort(key=lambda r: (-r["time_saved"], r["label"]))
    return out


def breakdown(conn: sqlite3.Connection, filters: Filters, *, by: str) -> dict[str, Any]:
    """Return per-group rollups of the filtered runs, ordered by time saved.

    Runs with no value for the dimension, such as runs recorded before gate-cache kept a
    branch, form their own labeled row.

    Args:
        conn: Archive connection.
        filters: Repo and range filters.
        by: The dimension to group by, one of DIMENSIONS.

    Returns:
        The dimension and its rows. Each row's `key` is opaque; pass it to `activity` as
        `group` to list that row's runs.

    Raises:
        ValueError: If the dimension is unknown.
    """
    where, params = _where(filters)
    return {"by": by, "rows": _breakdown_rows(conn, where, params, by)}


def _parse_cursor(cursor: str) -> tuple[float, int]:
    """Parse an activity cursor of the form "<ts>:<id>" or raise ValueError."""
    ts_text, _, id_text = cursor.rpartition(":")
    if NUMBER_RE.fullmatch(ts_text) and _INTEGER_RE.fullmatch(id_text):
        ts, event_id = float(ts_text), int(id_text)
    else:
        ts, event_id = math.nan, 0
    if not math.isfinite(ts) or not -(2**63) <= event_id < 2**63:
        msg = f"malformed cursor: {cursor!r}"
        raise ValueError(msg)
    return ts, event_id


def activity(  # noqa: PLR0913
    conn: sqlite3.Connection,
    filters: Filters,
    *,
    limit: int = 100,
    before: str | None = None,
    outcomes: Sequence[str] = (),
    reasons: Sequence[str] = (),
    group: tuple[str, str] | None = None,
    gates: Sequence[tuple[str | None, str]] = (),
    flaky: bool = False,
    spot_check: bool = False,
) -> dict[str, Any]:
    """Return one page of events, newest first.

    Args:
        conn: Archive connection.
        filters: Repo and range filters.
        limit: Page size, clamped to 1..500.
        before: Opaque cursor from a previous page's next_before.
        outcomes: Keep only events with one of these outcomes, or every event when empty.
        reasons: Keep only events with exactly one of these reasons, or every event when empty.
        group: Keep only the events of one breakdown row, as its dimension and key.
        gates: Keep only events of one of these (repo, gate) pairs, the gate being the name
            before any `@` key; None as the repo is the unknown repo. Empty keeps every gate.
        flaky: Keep only events on trees that both failed and passed in the window.
        spot_check: Keep only spot-check runs.

    Returns:
        The events and the cursor for the next page, or None on the last page.

    Raises:
        ValueError: If the cursor or group is malformed or an outcome is unknown.
    """
    limit = max(1, min(limit, _MAX_PAGE))
    where, params = _where(filters)
    unknown = [o for o in outcomes if o not in _OUTCOMES]
    if unknown:
        msg = f"unknown outcome: {unknown[0]!r}"
        raise ValueError(msg)
    where, params = _with_gates(where, params, gates)
    prefix, prefix_params = "", []
    if flaky:
        # Flakiness is decided over every outcome in the window, whatever else is filtered.
        tree_where, prefix_params = _with_gates(*_where(filters), gates)
        prefix = _flaky_trees_cte(tree_where)
        where = _and(where, _ON_FLAKY_TREE)
    if spot_check:
        where = _and(where, "spot_check = 1")
    if outcomes:
        where = _and(where, _in("outcome", outcomes))
        params = [*params, *outcomes]
    if reasons:
        where = _and(where, _in("reason", reasons))
        params = [*params, *reasons]
    if group is not None:
        condition, values = group_filter(by=group[0], key=group[1])
        where = _and(where, condition)
        params = [*params, *values]
    if before is not None:
        ts, event_id = _parse_cursor(before)
        where = _and(where, "(ts < ? OR (ts = ? AND id < ?))")
        params = [*params, ts, ts, event_id]
    names = all_repo_names(conn)
    rows = conn.execute(
        f"{prefix}SELECT {_ROW_COLUMNS}, id FROM events{where} ORDER BY ts DESC, id DESC LIMIT ?",  # noqa: S608
        [*prefix_params, *params, limit + 1],
    ).fetchall()
    page = rows[:limit]
    more = len(rows) > limit
    return {
        "events": [_event_row(r[:-1], names) for r in page],
        "next_before": f"{page[-1][0]!r}:{page[-1][-1]}" if more else None,
    }


def reasons(conn: sqlite3.Connection, filters: Filters) -> dict[str, Any]:
    """Return why gates ran without the cache, most common first."""
    where, params = _where(filters)
    rows = conn.execute(
        "SELECT outcome, reason, COUNT(*) AS n FROM events"  # noqa: S608
        + _and(where, "outcome IN ('uncached', 'pass_unrecorded') AND reason IS NOT NULL")
        + " GROUP BY outcome, reason ORDER BY n DESC, reason, outcome",
        params,
    ).fetchall()
    return {"reasons": [{"outcome": o, "reason": r, "count": n} for o, r, n in rows]}


TriageReason = Literal["flaky", "failed_spot_check"]
# The newest failed spot checks a triage row shows; the row still counts every one.
_SPOT_CHECK_EVIDENCE = 10


@dataclass(frozen=True)
class _TriageScope:
    """What every triage reason reads: the archive, the filtered events, and repo labels."""

    conn: sqlite3.Connection
    where: str
    params: list[Any]
    names: dict[str | None, str]
    # The oldest event time whose per-test results are kept.
    tests_since: float


# CROSS JOIN keeps SQLite from scanning every test result: the window's events lead and
# their results come through the event_id index.
def _flaky_results(where: str) -> str:
    """Return a subquery `f` of each test that both failed and passed on one flaky tree.

    Its parameters are `where`'s, then `since`; the `_flaky_trees_cte` it reads from comes first.
    """
    return (
        "(SELECT e.repo, e.gate, test_results.test_id,"  # noqa: S608
        " SUM(test_results.outcome = 'fail') AS fails,"
        " SUM(test_results.outcome IN " + _TEST_PASSED + ") AS passes, MAX(e.ts) AS last"
        " FROM (SELECT id, repo, gate, name, tree, ts FROM events"
        + _and(where, "tree IS NOT NULL AND ts >= ? AND " + _ON_FLAKY_TREE)
        + ") AS e CROSS JOIN test_results ON test_results.event_id = e.id"
        " GROUP BY e.repo, e.name, e.tree, test_results.test_id"
        " HAVING fails > 0 AND passes > 0) AS f"
    )


def _retried_results(where: str) -> str:
    """Return a subquery `r` of each retried test result, with its run's gate and time."""
    return (
        "(SELECT e.repo, e.gate, e.ts, test_results.test_id"  # noqa: S608
        " FROM (SELECT id, repo, gate, ts FROM events"
        + _and(where, "ts >= ? AND " + _NOT_SPOT_CHECK)
        + ") AS e"
        " CROSS JOIN test_results ON test_results.event_id = e.id"
        " WHERE test_results.outcome = 'retried') AS r"
    )


def _flaky_tests(
    conn: sqlite3.Connection, where: str, params: list[Any], *, since: float
) -> dict[tuple[str | None, str], list[dict[str, Any]]]:
    """Return, per gate, the tests that both failed and passed on one of its flaky trees."""
    out: dict[tuple[str | None, str], list[dict[str, Any]]] = defaultdict(list)
    for repo, gate, test, fails, passes, last in conn.execute(
        _flaky_trees_cte(where)  # noqa: S608
        + "SELECT f.repo, f.gate, tests.name, SUM(f.fails), SUM(f.passes), MAX(f.last) FROM "
        + _flaky_results(where)
        + " JOIN tests ON tests.id = f.test_id"
        " GROUP BY f.test_id ORDER BY MAX(f.last) DESC, tests.name",
        [*params, *params, since],
    ):
        out[repo, gate].append({"name": test, "fails": fails, "passes": passes, "last": last})
    return out


def _retried_tests(
    conn: sqlite3.Connection, where: str, params: list[Any], *, since: float
) -> dict[tuple[str | None, str], list[dict[str, Any]]]:
    """Return, per gate, the tests that passed on a retry."""
    out: dict[tuple[str | None, str], list[dict[str, Any]]] = defaultdict(list)
    for repo, gate, test, runs, last in conn.execute(
        "SELECT r.repo, r.gate, tests.name, COUNT(*), MAX(r.ts) FROM "  # noqa: S608
        + _retried_results(where)
        + " JOIN tests ON tests.id = r.test_id"
        " GROUP BY tests.id ORDER BY MAX(r.ts) DESC, tests.name",
        [*params, since],
    ):
        out[repo, gate].append({"name": test, "runs": runs, "last": last})
    return out


def _test_counts(
    conn: sqlite3.Connection, where: str, params: list[Any], *, since: float
) -> dict[GateKey, tuple[int, int]]:
    """Return, per gate, how many tests were flaky and how many passed on a retry."""
    out: dict[GateKey, list[int]] = defaultdict(lambda: [0, 0])
    for repo, gate, count in conn.execute(
        _flaky_trees_cte(where)  # noqa: S608
        + "SELECT repo, gate, COUNT(DISTINCT test_id) FROM "
        + _flaky_results(where)
        + " GROUP BY repo, gate",
        [*params, *params, since],
    ):
        out[repo, gate][0] = count
    for repo, gate, count in conn.execute(
        "SELECT repo, gate, COUNT(DISTINCT test_id) FROM "  # noqa: S608
        + _retried_results(where)
        + " GROUP BY repo, gate",
        [*params, since],
    ):
        out[repo, gate][1] = count
    return {key: (flaky_count, retried) for key, (flaky_count, retried) in out.items()}


def _flaky_items(scope: _TriageScope) -> list[dict[str, Any]]:
    """Return one triage row per gate with flaky trees or retried tests, its trees newest first.

    The evidence lists the flaky trees with their runs, the tests that both failed and passed on
    one of those trees, and the tests that passed on a retry.
    """
    conn, where, params, names = scope.conn, scope.where, scope.params, scope.names
    runs: dict[tuple[str | None, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in conn.execute(
        f"{_flaky_trees_cte(where)}SELECT {_ROW_COLUMNS} FROM events"  # noqa: S608
        + _and(where, _ON_FLAKY_TREE)
        + " ORDER BY ts, id",
        [*params, *params],
    ):
        event = _event_row(row, names)
        runs[event["repo"], event["gate"], event["tree"]].append(event)
    last_seen = {key: max(run["ts"] for run in tree_runs) for key, tree_runs in runs.items()}
    by_gate: dict[tuple[str | None, str], list[tuple[str, float]]] = defaultdict(list)
    for repo, gate, tree in sorted(last_seen, key=lambda k: (-last_seen[k], k[2])):
        by_gate[repo, gate].append((tree, last_seen[repo, gate, tree]))
    tests = _flaky_tests(conn, where, params, since=scope.tests_since)
    retried = _retried_tests(conn, where, params, since=scope.tests_since)
    return [
        {
            "repo": repo,
            "repo_name": names[repo],
            "name": gate,
            "reason": "flaky",
            "last_seen": max(
                [last for _, last in by_gate[repo, gate]] + [t["last"] for t in retried[repo, gate]]
            ),
            "evidence": {
                "trees": [
                    {"tree": tree, "runs": runs[repo, gate, tree]}
                    for tree, _ in by_gate[repo, gate]
                ],
                "tests": tests[repo, gate],
                "retried": retried[repo, gate],
            },
        }
        for repo, gate in dict.fromkeys([*by_gate, *retried])
    ]


def _failed_spot_check_items(scope: _TriageScope) -> list[dict[str, Any]]:
    """Return one triage row per gate with failed spot checks, the newest of them first."""
    conn, where, params, names = scope.conn, scope.where, scope.params, scope.names
    runs: dict[tuple[str | None, str], list[dict[str, Any]]] = defaultdict(list)
    counts: dict[tuple[str | None, str], int] = {}
    for *row, count in conn.execute(
        f"SELECT {_ROW_COLUMNS}, n FROM ("  # noqa: S608
        f"SELECT {_ROW_COLUMNS}, id,"
        " ROW_NUMBER() OVER (PARTITION BY repo, gate ORDER BY ts DESC, id DESC) AS pos,"
        " COUNT(*) OVER (PARTITION BY repo, gate) AS n"
        " FROM events"
        + _and(where, _FAILED_SPOT_CHECK)
        + ") WHERE pos <= ? ORDER BY ts DESC, id DESC",
        [*params, _SPOT_CHECK_EVIDENCE],
    ):
        event = _event_row(tuple(row), names)
        key = (event["repo"], event["gate"])
        runs[key].append(event)
        counts[key] = count
    return [
        {
            "repo": repo,
            "repo_name": names[repo],
            "name": gate,
            "reason": "failed_spot_check",
            "last_seen": gate_runs[0]["ts"],
            "evidence": {"count": counts[repo, gate], "runs": gate_runs},
        }
        for (repo, gate), gate_runs in runs.items()
    ]


# Each reason a gate needs a look, in the order a tie on last_seen lists them. A new reason adds
# one entry here and one in the dashboard.
_TRIAGE_REASONS: dict[TriageReason, Callable[[_TriageScope], list[dict[str, Any]]]] = {
    "flaky": _flaky_items,
    "failed_spot_check": _failed_spot_check_items,
}


def triage(
    conn: sqlite3.Connection,
    filters: Filters,
    *,
    reason: TriageReason | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Return the gates that need a look, one row per gate and reason, newest first.

    A gate with several reasons gets a row for each, so each row carries the evidence that fits
    its reason: the flaky trees, their runs, and the tests that flaked, or the failed spot checks.

    Args:
        conn: Archive connection.
        filters: Repo and range filters.
        reason: Build only this reason's rows, or every reason's when None.
        now: Current Unix time in seconds; defaults to the clock.

    Returns:
        The triage rows, and where per-test retention starts when the window reaches further
        back.

    Raises:
        ValueError: If the reason is unknown.
    """
    if reason is not None and reason not in _TRIAGE_REASONS:
        msg = f"unknown triage reason: {reason!r}"
        raise ValueError(msg)
    where, params = _where(filters)
    since = tests_since(time.time() if now is None else now)
    scope = _TriageScope(conn, where, params, all_repo_names(conn), since)
    order = list(_TRIAGE_REASONS)
    builders = [_TRIAGE_REASONS[reason]] if reason is not None else _TRIAGE_REASONS.values()
    items = [item for build in builders for item in build(scope)]
    items.sort(key=lambda i: (-i["last_seen"], order.index(i["reason"]), i["name"]))
    return {"items": items, "tests_cutoff": _tests_cutoff(filters, since)}


def gate_flaky_counts(
    conn: sqlite3.Connection, filters: Filters
) -> dict[tuple[str | None, str], dict[str, Any]]:
    """Return flaky tree, fail, and pass counts per gate, with the newest flaky run."""
    where, params = _where(filters)
    out: dict[tuple[str | None, str], dict[str, Any]] = {}
    for repo, gate, _tree, fails, passes, last in _flaky_trees(conn, where, params):
        entry = out.setdefault(
            (repo, gate), {"trees": 0, "fails": 0, "passes": 0, "last_seen": last}
        )
        entry["trees"] += 1
        entry["fails"] += fails
        entry["passes"] += passes
        entry["last_seen"] = max(entry["last_seen"], last)
    return out


def gate_tests(
    conn: sqlite3.Connection,
    filters: Filters,
    *,
    repo: str | None,
    name: str,
    since: float,
    gate_median: float | None,
) -> dict[str, Any] | None:
    """Return one gate's per-test detail: slowest, flaky, and retried tests, and report problems.

    Args:
        conn: Archive connection.
        filters: Range filters; its repo is ignored.
        repo: The gate's repo.
        name: Gate, the name before any `@` key.
        since: Oldest event time whose per-test results are kept.
        gate_median: The gate's median passing duration over `filters`, for each test's share.

    Returns:
        The detail with every slowest test and report problems under their report keys, or None
        when the gate never recorded test results and its recent runs had no report problem.
    """
    where, params = _where(filters, gate=name, exact_repo=(repo,))
    key = (repo, name)
    problems = _report_problem_counts(conn, where, params).get(key)
    if problems is None and not _has_tests(conn, repo=repo, name=name):
        return None
    problems = problems or dict.fromkeys(_REPORT_PROBLEMS, 0)
    return {
        "since": _tests_cutoff(filters, since),
        "slowest": _slowest_tests(
            conn, where, params, gate_median=gate_median, since=since, limit=None
        ),
        "flaky": _flaky_tests(conn, where, params, since=since).get(key, []),
        "retried": _retried_tests(conn, where, params, since=since).get(key, []),
        "report_problems": {_REPORT_PROBLEM_KEYS[k]: problems[k] for k in _REPORT_PROBLEMS},
    }


def gate_test_counts(
    conn: sqlite3.Connection, filters: Filters, *, since: float
) -> dict[GateKey, dict[str, int]]:
    """Return, per gate, how many tests were flaky or retried and how many runs had report problems.

    Only gates that recorded test results, or whose recent runs had a report problem, appear.
    """
    where, params = _where(filters)
    problems = _report_problem_counts(conn, where, params)
    counts = _test_counts(conn, where, params, since=since)
    return {
        key: {
            "flaky": counts.get(key, (0, 0))[0],
            "retried": counts.get(key, (0, 0))[1],
            "report_problems": sum(problems.get(key, {}).values()),
        }
        for key in _gates_with_tests(conn) | problems.keys()
    }


def _gates_with_tests(conn: sqlite3.Connection) -> set[GateKey]:
    """Return every gate that ever recorded test results."""
    return {(repo, gate) for repo, gate in conn.execute("SELECT DISTINCT repo, gate FROM tests")}


def _has_tests(conn: sqlite3.Connection, *, repo: str | None, name: str) -> bool:
    """Return whether the gate ever recorded test results."""
    (found,) = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM tests WHERE repo IS ? AND gate = ?)", (repo, name)
    ).fetchone()
    return bool(found)


def gate_uncached(
    conn: sqlite3.Connection, filters: Filters, *, gate_key: GateKey | None = None
) -> dict[GateKey, list[dict[str, Any]]]:
    """Return why each gate ran without the cache, most common first.

    Args:
        conn: Archive connection.
        filters: Repo and range filters.
        gate_key: One gate's (repo, name) to scan alone; None covers every gate in `filters`.
    """
    where, params = _gate_where(filters, gate_key)
    rows = conn.execute(
        "SELECT repo, gate, outcome, reason, COUNT(*) AS n FROM events"  # noqa: S608
        + _and(where, "outcome IN ('uncached', 'pass_unrecorded') AND reason IS NOT NULL")
        + " GROUP BY repo, gate, outcome, reason ORDER BY n DESC, reason, outcome",
        params,
    )
    out: dict[tuple[str | None, str], list[dict[str, Any]]] = {}
    for repo, gate, outcome, reason, count in rows:
        out.setdefault((repo, gate), []).append(
            {"outcome": outcome, "reason": reason, "count": count}
        )
    return out


def gate_overhead(
    conn: sqlite3.Connection, filters: Filters, *, gate_key: GateKey | None = None
) -> dict[GateKey, float]:
    """Return the seconds gate-cache itself spent around each gate's runs.

    Args:
        conn: Archive connection.
        filters: Repo and range filters.
        gate_key: One gate's (repo, name) to scan alone; None covers every gate in `filters`.
    """
    where, params = _gate_where(filters, gate_key)
    rows = conn.execute(
        "SELECT repo, gate, COALESCE(SUM(overhead), 0.0) FROM events"  # noqa: S608
        + where
        + " GROUP BY repo, gate",
        params,
    )
    return {(repo, gate): float(total) for repo, gate, total in rows}


def gate_latest_command(
    conn: sqlite3.Connection, filters: Filters
) -> dict[tuple[str | None, str], tuple[str, list[str]]]:
    """Return each gate's newest command, falling back to its name, and its watched paths."""
    where, params = _where(filters)
    rows = conn.execute(
        "SELECT repo, gate, command, paths FROM ("  # noqa: S608
        "SELECT repo, gate, COALESCE(" + _raw_text("command") + ", name) AS command, paths,"
        " ROW_NUMBER() OVER (PARTITION BY repo, gate ORDER BY ts DESC, id DESC) AS rn"
        " FROM events" + where + ") WHERE rn = 1",
        params,
    )
    return {(repo, gate): (command, json.loads(paths)) for repo, gate, command, paths in rows}


def gate_command(
    conn: sqlite3.Connection, *, repo: str | None, name: str
) -> tuple[str, list[str]] | None:
    """Return one gate's newest command and paths over the whole record.

    Returns:
        The command, or the name when the run recorded none, and the watched paths. None
        when the repo never recorded the gate.
    """
    where, params = _where(Filters(), gate=name, exact_repo=(repo,))
    command = _raw_text("command")
    row = conn.execute(
        f"SELECT COALESCE({command}, name), paths FROM events{where}"  # noqa: S608
        " ORDER BY ts DESC, id DESC LIMIT 1",
        params,
    ).fetchone()
    return None if row is None else (row[0], json.loads(row[1]))


def _bucket_date(day: date, bucket: Bucket) -> date:
    """Return the first day of the week (Monday) or month holding a day, or the day itself."""
    if bucket == "week":
        return day - timedelta(days=day.weekday())
    if bucket == "month":
        return day.replace(day=1)
    return day


def gate_trend(
    conn: sqlite3.Connection,
    filters: Filters,
    *,
    repo: str | None,
    name: str,
    bucket: Bucket,
    tz: ZoneInfo,
) -> list[dict[str, Any]]:
    """Return runs and passing-duration spread per local day, week, or month, oldest first.

    Args:
        conn: Archive connection.
        filters: Range filters; its repo is ignored.
        repo: The gate's repo; None selects events recorded without a repo.
        name: Gate, as stats group it: the name before any `@` key.
        bucket: `day`, `week`, or `month`.
        tz: Zone that decides where each bucket starts.

    Returns:
        One row per bucket that holds an event.
    """
    where, params = _where(filters, gate=name, exact_repo=(repo,))
    runs: Counter[date] = Counter()
    passes: dict[date, list[float]] = defaultdict(list)
    for ts, outcome, duration in conn.execute(
        "SELECT ts, outcome, duration FROM events" + where,  # noqa: S608
        params,
    ):
        start = _bucket_date(datetime.fromtimestamp(ts, tz).date(), bucket)
        runs[start] += 1
        if outcome == "pass" and duration is not None:
            passes[start].append(duration)
    return [
        {
            "start": start.isoformat(),
            "runs": runs[start],
            "median": _run_stats(passes[start])[1],
            "p90": _p90(passes[start]),
        }
        for start in sorted(runs)
    ]


def gate_exit_codes(
    conn: sqlite3.Connection, filters: Filters, *, repo: str | None, name: str
) -> dict[str, int]:
    """Return how often each exit code ended a failed run, most common first."""
    where, params = _where(filters, gate=name, exact_repo=(repo,))
    rows = conn.execute(
        "SELECT exit_code, COUNT(*) AS n FROM events"  # noqa: S608
        + _and(where, "outcome = 'fail' AND exit_code IS NOT NULL")
        + " GROUP BY exit_code ORDER BY n DESC, exit_code",
        params,
    )
    return {str(code): count for code, count in rows}


def gate_dimensions(
    conn: sqlite3.Connection, filters: Filters, *, repo: str | None, name: str
) -> dict[str, list[dict[str, Any]]]:
    """Return the gate's runs grouped by source, branch, and machine, most runs first.

    A run whose raw line lacks a field groups under `None` for that field.
    """
    where, params = _where(filters, gate=name, exact_repo=(repo,))
    trigger, agent = _raw_text("trigger"), _raw_text("agent")
    branch, machine, host = _raw_text("branch"), _raw_text("machine"), _raw_text("host")
    counts = "COUNT(*), SUM(outcome = 'fail')"
    order = " ORDER BY COUNT(*) DESC, 1, 2"

    sources = conn.execute(
        f"SELECT {trigger}, {agent}, {counts}, COALESCE(SUM(duration), 0.0)"  # noqa: S608
        f" FROM events{where} GROUP BY 1, 2{order}",
        params,
    )
    branches = conn.execute(
        f"SELECT {branch}, {counts} FROM events{where} GROUP BY 1{order}",  # noqa: S608
        params,
    )
    # With a lone MAX(), SQLite takes the other bare columns from the row that holds the maximum,
    # so each machine reports the host of its newest run.
    machines = conn.execute(
        f"SELECT {machine}, {counts}, {host}, MAX(ts) FROM events{where} GROUP BY 1{order}",  # noqa: S608
        params,
    )
    return {
        "sources": [
            {
                "source": source,
                "agent": who,
                "runs": runs,
                "failures": failures,
                "time_spent": float(spent),
            }
            for source, who, runs, failures, spent in sources
        ],
        "branches": [
            {"branch": b, "runs": runs, "failures": failures} for b, runs, failures in branches
        ],
        "machines": [
            {"machine": m, "host": h, "runs": runs, "failures": failures}
            for m, runs, failures, h, _newest in machines
        ],
    }


_COMMIT_LENGTH = 7
_RUN_KEYS = (
    "ts",
    "name",
    "outcome",
    "exit_code",
    "duration",
    "tree",
    "commit",
    "branch",
    "source",
    "agent",
    "machine",
    "spot_check",
)


def gate_runs(
    conn: sqlite3.Connection,
    filters: Filters,
    *,
    repo: str | None,
    name: str,
    limit: int,
    tree: str | None = None,
    failed_spot_checks: bool = False,
) -> tuple[int, list[dict[str, Any]]]:
    """Return the gate's event count and its newest events, optionally for one tree.

    Each event carries its `id`, for `failed_tests`. A tree's runs leave out spot checks, as
    the flaky views do.

    Args:
        conn: Archive connection.
        filters: Range filters.
        repo: The gate's repo.
        name: Gate, the name before any `@` key.
        limit: Most events to return; the count covers every match.
        tree: Keep only this tree's runs, leaving out spot checks.
        failed_spot_checks: Keep only the spot checks that failed.
    """
    where, params = _where(filters, gate=name, exact_repo=(repo,))
    if tree is not None:
        where = _and(where, "tree = ? AND " + _NOT_SPOT_CHECK)
        params = [*params, tree]
    if failed_spot_checks:
        where = _and(where, _FAILED_SPOT_CHECK)
    (total,) = conn.execute("SELECT COUNT(*) FROM events" + where, params).fetchone()  # noqa: S608
    rows = conn.execute(
        "SELECT id, ts, name, outcome, exit_code, duration, tree, "  # noqa: S608
        f"NULLIF(substr({_raw_text('head')}, 1, {_COMMIT_LENGTH}), ''), "
        + ", ".join(_raw_text(f) for f in ("branch", "trigger", "agent", "machine"))
        + ", spot_check FROM events"
        + where
        + " ORDER BY ts DESC, id DESC LIMIT ?",
        [*params, limit],
    )
    runs = [dict(zip(("id", *_RUN_KEYS), row, strict=True)) for row in rows]
    for run in runs:
        run["spot_check"] = bool(run["spot_check"])
    return total, runs


def failed_tests(
    conn: sqlite3.Connection, event_ids: list[int]
) -> dict[int, tuple[int, list[str]]]:
    """Return, per run that recorded test results, its failed test count and first names.

    Take the ids of many runs at once, so a report that shows several lists of runs reads
    their test results in one query.

    A run whose results hold no failure maps to a zero count and no names.
    """
    if not event_ids:
        return {}
    out: dict[int, tuple[int, list[str]]] = {}
    # Failed results sort first, so the cut keeps them and a run with none still yields a row.
    for event_id, test, failed, fails in conn.execute(
        "SELECT event_id, name, failed, fails FROM ("
        " SELECT test_results.event_id AS event_id, tests.name AS name,"
        " test_results.outcome = 'fail' AS failed,"
        " SUM(test_results.outcome = 'fail') OVER (PARTITION BY test_results.event_id) AS fails,"
        " ROW_NUMBER() OVER (PARTITION BY test_results.event_id"
        " ORDER BY test_results.outcome != 'fail', tests.name) AS rn"
        " FROM test_results JOIN tests ON tests.id = test_results.test_id"
        # One JSON parameter, so a long id list never hits SQLite's bound-parameter limit.
        " WHERE test_results.event_id IN (SELECT value FROM json_each(?)))"
        " WHERE rn <= ? ORDER BY event_id, rn",
        [json.dumps(sorted(set(event_ids))), FAILED_TESTS_SHOWN],
    ):
        _, names = out.setdefault(event_id, (fails, []))
        if failed:
            names.append(test)
    return out


def gate_variants(
    conn: sqlite3.Connection, filters: Filters, *, repo: str | None, name: str
) -> list[dict[str, Any]]:
    """Return every keyed name (`name@key`) the gate ever recorded, with its runs in the range.

    Each name carries the paths of its own newest run over the whole record, since keys of
    one gate can watch different paths. A name with runs in the range comes first, newest
    run first; a name with none has `runs` 0 and `last_run` None.
    """
    where, params = _where(Filters(), gate=name, exact_repo=(repo,))
    bounds = [
        (clause, value)
        for clause, value in (("ts >= ?", filters.start), ("ts < ?", filters.end))
        if value is not None
    ]
    in_range = " AND ".join(clause for clause, _ in bounds) or "1"
    range_params = [value for _, value in bounds]
    rows = conn.execute(
        "SELECT name, paths, runs, last FROM ("  # noqa: S608
        "SELECT name, paths,"
        " ROW_NUMBER() OVER (PARTITION BY name ORDER BY ts DESC, id DESC) AS rn,"
        f" SUM({in_range}) OVER (PARTITION BY name) AS runs,"
        f" MAX(CASE WHEN {in_range} THEN ts END) OVER (PARTITION BY name) AS last"
        " FROM events" + _and(where, "name <> gate") + ") WHERE rn = 1",
        [*range_params, *range_params, *params],
    )
    variants = [
        {"name": n, "runs": runs, "last_run": last, "paths": json.loads(paths)}
        for n, paths, runs, last in rows
    ]
    variants.sort(key=lambda v: (v["last_run"] is None, -(v["last_run"] or 0), v["name"]))
    return variants


def gate_summary(
    conn: sqlite3.Connection, filters: Filters, *, repo: str | None, name: str
) -> dict[str, Any]:
    """Return the gate's totals, run times, resource use, and spot checks over the range."""
    where, params = _where(filters, gate=name, exact_repo=(repo,))
    row = next(iter(_gate_rows(conn, where, params)), None)
    keys = (*SUMMARY_KEYS, "cpu_ratio", "peak_rss", "median_rss", *SPOT_CHECK_KEYS)
    out = {key: row[key] if row else None for key in keys}
    if row is None:
        out.update(runs=0, failures=0, time_spent=0.0, time_saved=0.0, fail_time=0.0)
        out.update(dict.fromkeys(SPOT_CHECK_KEYS, 0))
    out["overhead"] = gate_overhead(conn, filters, gate_key=(repo, name)).get((repo, name), 0.0)
    return out
