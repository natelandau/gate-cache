"""Compute the dashboard metrics from the archive."""

from __future__ import annotations

import json
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, get_args
from zoneinfo import ZoneInfo

from gate_cache.stats.archive import RETENTION_DAYS
from gate_cache.stats.recorder import Outcome

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable, Iterable, Iterator

_RAN = "('skip', 'pass', 'pass_unrecorded', 'fail')"
_GOOD = "('pass', 'pass_unrecorded')"
_RECENT_LIMIT = 50
_TOP_SPENT = 5
_MAX_PAGE = 500
_OUTCOMES: frozenset[str] = frozenset(get_args(Outcome))
# The archive keeps outcomes from newer gate-cache versions; only known ones count.
_KNOWN = "outcome IN (" + ", ".join(f"'{o}'" for o in sorted(_OUTCOMES)) + ")"
_ROW_COLUMNS = "ts, repo, name, outcome, duration, saved, exit_code, reason, tree, reported"
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


def _work_dir(repo: str) -> Path:
    """Return the folder that holds a repo's working copy, or the repo itself when bare."""
    path = Path(repo)
    return path.parent if path.name == ".git" else path


def _folder_name(repo: str | None) -> str:
    """Return a repo's folder name, which other repos may share."""
    return _UNKNOWN_REPO if repo is None else _work_dir(repo).name


def _parent_labels(name: str, clashing: list[str], taken: set[str]) -> list[str]:
    """Return the shortest run of parent folders that tells apart repos sharing a name.

    A label must also differ from every name in `taken`, the folder names other repos show.
    Fall back to each full path when the parents cannot tell them apart.
    """
    folders = [_work_dir(repo).parent for repo in clashing]
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


def _all_repo_names(conn: sqlite3.Connection) -> _RepoNames:
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
    name: str | None = None,
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
            parts.append(f"repo IN ({', '.join('?' * len(known))})")
            params.extend(known)
        if None in filters.repos:
            parts.append("repo IS NULL")
        clauses.append(f"({' OR '.join(parts)})")
    if name is not None:
        clauses.append("name = ?")
        params.append(name)
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


def _skip_rate(skips: int, ran: int) -> float | None:
    """Return skips over ran, or None when nothing ran."""
    return skips / ran if ran else None


# A flaky tree: one gate's content that both failed and passed. Every flaky view groups by this.
_FLAKY_GROUP = (
    " GROUP BY repo, name, tree"
    " HAVING SUM(outcome = 'fail') > 0 AND SUM(outcome IN " + _GOOD + ") > 0"
)
# Joins events to the flaky trees in `ft`, from _flaky_trees_cte.
_ON_FLAKY_TREE = (
    "EXISTS (SELECT 1 FROM ft WHERE ft.repo IS events.repo AND ft.name = events.name"
    " AND ft.tree = events.tree)"
)


def _flaky_trees_cte(where: str) -> str:
    """Return a WITH clause naming `ft`, the flaky trees among events matching `where`.

    The aggregate keeps SQLite from flattening the CTE, so it runs once rather than once per
    event that joins to it.
    """
    return (
        "WITH ft AS (SELECT repo, name, tree FROM events"  # noqa: S608
        + _and(where, "tree IS NOT NULL")
        + _FLAKY_GROUP
        + ") "
    )


def _flaky_trees(
    conn: sqlite3.Connection, where: str, params: list[Any]
) -> list[tuple[str | None, str, str, int, int, float]]:
    """Return (repo, name, tree, fails, passes, last) for trees with a fail and a pass."""
    sql = (
        "SELECT repo, name, tree,"  # noqa: S608
        " SUM(outcome = 'fail'), SUM(outcome IN " + _GOOD + "), MAX(ts)"
        " FROM events"
        + _and(where, "tree IS NOT NULL")
        + _FLAKY_GROUP
        + " ORDER BY MAX(ts) DESC, tree"
    )
    return [(r[0], r[1], r[2], r[3], r[4], r[5]) for r in conn.execute(sql, params)]


def _event_row(raw: tuple[Any, ...], names: dict[str | None, str]) -> dict[str, Any]:
    """Convert a row selected with _ROW_COLUMNS into an API dict."""
    ts, repo, name, outcome, duration, saved, exit_code, reason, tree, reported = raw
    return {
        "ts": ts,
        "repo": repo,
        "repo_name": names[repo],
        "name": name,
        "outcome": outcome,
        "duration": duration,
        "saved": saved,
        "exit_code": exit_code,
        "reason": reason,
        "tree": tree,
        "reported": bool(reported),
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
        cost_unknown,
    ) = row
    return {
        "time_saved": float(saved),
        "unknown_saved_skips": unknown,
        "overhead": float(overhead),
        "waited": float(waited),
        "time_spent": float(time_spent),
        "fail_time": float(fail_time),
        "net_saved": float(saved) - float(overhead) - float(waited),
        "cost_unknown_runs": cost_unknown,
        "runs": runs,
        "skips": skips,
        "skip_rate": _skip_rate(skips, ran),
        "uncached": uncached,
        "failures": failures,
        "flaky_gates": len({(r[0], r[1]) for r in _flaky_trees(conn, where, params)}),
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
    """Runs, seconds saved by skips, and failures, summed over some events."""

    runs: int = 0
    saved: float = 0.0
    failures: int = 0

    def add(self, other: _Tally) -> None:
        """Add another tally's counts to this one."""
        self.runs += other.runs
        self.saved += other.saved
        self.failures += other.failures


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
    for bucket_id, saved, failures, runs in conn.execute(
        "SELECT " + _BUCKET + ","  # noqa: S608
        " COALESCE(SUM(CASE WHEN outcome = 'skip' THEN saved END), 0.0),"
        " SUM(outcome = 'fail'), COUNT(*)"
        " FROM events" + where + " GROUP BY 1",
        params,
    ):
        start = _bucket_start(bucket_id, zone)
        yield bucket_id, start, _Tally(runs=int(runs), saved=float(saved), failures=int(failures))


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
                "net_saved",
                "time_spent",
                "runs",
                "skips",
                "skip_rate",
                "failures",
                "flaky_gates",
            )
        }
        previous["days"] = (window.end - window.start) / 86400
        # Windows that leave out different costs cannot be compared.
        if result["cost_unknown_runs"] or totals["cost_unknown_runs"]:
            previous["net_saved"] = None
    days: dict[str, _Tally] = defaultdict(_Tally)
    for _, start, tally in _local_buckets(conn, filters):
        days[start.date().isoformat()].add(tally)
    return {
        **result,
        "previous": previous,
        "daily": [
            {"day": day, "saved": t.saved, "failures": t.failures, "runs": t.runs}
            for day, t in sorted(days.items())
        ],
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
    # A run that waited can still end uncached when its new snapshot has no tree key.
    row = conn.execute(
        "SELECT COALESCE(SUM(outcome IN " + _RAN + " OR waited IS NOT NULL), 0),"  # noqa: S608
        " COALESCE(SUM(outcome IN " + _RAN + " AND wait_known = 0), 0),"
        " COUNT(waited),"
        " COALESCE(SUM(waited IS NOT NULL AND outcome = 'skip'), 0),"
        " COALESCE(SUM(waited IS NOT NULL AND reported), 0),"
        " COALESCE(SUM(waited IS NOT NULL AND wait_timed_out), 0),"
        " COALESCE(SUM(waited), 0.0),"
        " COALESCE(SUM(CASE WHEN waited IS NOT NULL AND outcome = 'skip' THEN saved END), 0.0),"
        # Each wait, for the median, collected in the same pass over the range.
        " json_group_array(waited) FILTER (WHERE waited IS NOT NULL)"
        " FROM events" + where,
        params,
    ).fetchone()
    checked, unknown, waited, skipped, reported, timed_out, total_wait, saved, waits_json = row
    waits = json.loads(waits_json)
    return {
        "runs": checked,
        "unknown_runs": unknown,
        "waited": waited,
        "skipped": skipped,
        "reported": reported,
        "ran": waited - skipped - reported,
        "timed_out": timed_out,
        "total_wait": float(total_wait),
        "median_wait": float(statistics.median(waits)) if waits else None,
        "saved": float(saved),
    }


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
    where, params = _where(filters)
    names = _all_repo_names(conn)
    flaky_keys = {(r[0], r[1]) for r in _flaky_trees(conn, where, params)}
    durations = _pass_durations(conn, where, params)
    resources = _resource_costs(conn, where, params)
    rows = conn.execute(
        "SELECT repo, name, COUNT(*),"  # noqa: S608
        " SUM(outcome = 'skip'), SUM(outcome IN " + _RAN + "),"
        " COALESCE(SUM(CASE WHEN outcome = 'skip' THEN saved END), 0.0),"
        " SUM(outcome = 'fail'), MAX(ts), COALESCE(SUM(duration), 0.0),"
        " COALESCE(SUM(CASE WHEN outcome = 'fail' THEN duration END), 0.0)"
        " FROM events" + where + " GROUP BY repo, name",
        params,
    ).fetchall()
    out: list[dict[str, Any]] = []
    for repo, name, runs, skips, ran, saved, failures, last, spent, fail_time in rows:
        durs = durations.get((repo, name), [])
        avg_run, median_run = _run_stats(durs)
        cpu_ratio, peak_rss, rss_values = resources.get((repo, name), (None, None, []))
        out.append(
            {
                "repo": repo,
                "repo_name": names[repo],
                "name": name,
                "runs": runs,
                "skip_rate": _skip_rate(skips, ran),
                "avg_run": avg_run,
                "median_run": median_run,
                "time_saved": float(saved),
                "failures": failures,
                "last_run": last,
                "flaky": (repo, name) in flaky_keys,
                "time_spent": float(spent),
                "fail_time": float(fail_time),
                "p90_run": _p90(durs),
                "cpu_ratio": cpu_ratio,
                "peak_rss": peak_rss,
                "median_rss": float(statistics.median(rss_values)) if rss_values else None,
            }
        )
    out.sort(key=lambda g: (-g["time_saved"], g["repo_name"], g["name"]))
    return {"gates": out}


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
    names = _all_repo_names(conn)
    totals: dict[tuple[str | None, str], float] = defaultdict(float)
    cells: dict[str, dict[tuple[str | None, str], float]] = defaultdict(lambda: defaultdict(float))
    days: dict[int, str] = {}
    for repo, name, bucket_id, seconds in conn.execute(
        "SELECT repo, name, " + _BUCKET + ", SUM(duration)"  # noqa: S608
        " FROM events" + where + " GROUP BY repo, name, 3",
        params,
    ):
        key = (repo, name)
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
                "name": name,
                "label": f"{name} · {names[repo]}" if multi_repo else name,
                "total": totals[(repo, name)],
            }
            for repo, name in top
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
    for repo, name, duration in conn.execute(
        "SELECT repo, name, duration FROM events"  # noqa: S608
        + _and(where, "outcome = 'pass' AND duration IS NOT NULL"),
        params,
    ):
        durations[(repo, name)].append(duration)
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
    for repo, name, duration, cpu, rss in conn.execute(
        "SELECT repo, name, duration,"  # noqa: S608
        " CASE WHEN json_valid(raw) THEN json_extract(raw, '$.cpu') END,"
        " CASE WHEN json_valid(raw) THEN json_extract(raw, '$.max_rss') END"
        # Only runs that ran the command record usage, so skips need no JSON parsing.
        " FROM events" + _and(where, "duration IS NOT NULL"),
        params,
    ):
        gate = totals[(repo, name)]
        if _is_number(cpu):
            gate.cpu += cpu
            gate.wall += duration
            gate.has_cpu = True
        if _is_number(rss):
            gate.rss.append(int(rss))
    return {
        key: (
            gate.cpu / gate.wall if gate.has_cpu and gate.wall else None,
            max(gate.rss) if gate.rss else None,
            gate.rss,
        )
        for key, gate in totals.items()
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
    names = _all_repo_names(conn)
    current = replace(filters, end=filters.end if filters.end is not None else current_time)
    before = _median_passes(conn, window)
    after = _median_passes(conn, current)
    out: list[dict[str, Any]] = []
    for (repo, name), (median_now, runs_now) in after.items():
        median_before, runs_before = before.get((repo, name), (0.0, 0))
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
                "name": name,
                "before": median_before,
                "now": median_now,
                "change": median_now / median_before - 1,
            }
        )
    out.sort(key=lambda g: (-g["change"], g["repo_name"], g["name"]))
    return {"gates": out[:limit], "comparable": True}


def gate_detail(
    conn: sqlite3.Connection, filters: Filters, *, repo: str | None, name: str
) -> dict[str, Any]:
    """Return the pass trend, recent events, and flaky trees of one gate.

    Args:
        conn: Archive connection.
        filters: Range filters; its repo is ignored.
        repo: The gate's repo; None selects events recorded without a repo.
        name: Gate name.

    Returns:
        The detail body.
    """
    where, params = _where(filters, name=name, exact_repo=(repo,))
    names = _all_repo_names(conn)
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
        "flaky_trees": [
            {"tree": tree, "fails": fails, "passes": passes, "last": last}
            for _, _, tree, fails, passes, last in _flaky_trees(conn, where, params)
        ],
    }


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
    "gate": _Grouping(("repo", "name"), _gate_labels, in_repo=True),
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
    names = _all_repo_names(conn) if names is None else names
    # With exactly one MAX aggregate, SQLite takes the bare `extra` value from that newest row.
    rows = conn.execute(
        "SELECT " + ", ".join(grouping.columns) + ","  # noqa: S608
        f" {grouping.extra or 'NULL'}, MAX(ts),"
        " COUNT(*), SUM(outcome = 'skip'), SUM(outcome IN " + _RAN + "),"
        " COALESCE(SUM(CASE WHEN outcome = 'skip' THEN saved END), 0.0),"
        " SUM(outcome = 'fail'), COUNT(DISTINCT json_array(repo, name)),"
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


def _hour_buckets(conn: sqlite3.Connection, filters: Filters, weekday: int, hour: int) -> list[int]:
    """Return the ids of the event buckets in a local weekday and hour.

    The buckets come from `_local_buckets`, as in `hourly`, so they hold exactly the events
    the heatmap cell counts.
    """
    return [
        bucket_id
        for bucket_id, start, _ in _local_buckets(conn, filters)
        if start.isoweekday() % 7 == weekday and start.hour == hour
    ]


def _check_slot(weekday: int | None, hour: int | None) -> None:
    """Raise ValueError unless weekday and hour are both absent or both in range."""
    if (weekday is None) != (hour is None):
        msg = f"weekday and hour go together: weekday={weekday!r}, hour={hour!r}"
        raise ValueError(msg)
    if weekday is not None and not 0 <= weekday <= 6:  # noqa: PLR2004
        msg = f"weekday must be 0 to 6: {weekday!r}"
        raise ValueError(msg)
    if hour is not None and not 0 <= hour <= 23:  # noqa: PLR2004
        msg = f"hour must be 0 to 23: {hour!r}"
        raise ValueError(msg)


def activity(  # noqa: PLR0913
    conn: sqlite3.Connection,
    filters: Filters,
    *,
    limit: int = 100,
    before: str | None = None,
    outcome: str | None = None,
    reason: str | None = None,
    group: tuple[str, str] | None = None,
    weekday: int | None = None,
    hour: int | None = None,
    gate: tuple[str | None, str] | None = None,
    flaky: bool = False,
) -> dict[str, Any]:
    """Return one page of events, newest first.

    Args:
        conn: Archive connection.
        filters: Repo and range filters.
        limit: Page size, clamped to 1..500.
        before: Opaque cursor from a previous page's next_before.
        outcome: Keep only events with this outcome, or every event when None.
        reason: Keep only events with exactly this reason, or every event when None.
        group: Keep only the events of one breakdown row, as its dimension and key.
        weekday: With `hour`, keep only events in this local weekday (0 is Sunday).
        hour: With `weekday`, keep only events in this local hour (0 to 23).
        gate: Keep only events of this repo and gate name; None as the repo is the unknown repo.
        flaky: Keep only events on trees that both failed and passed in the window.

    Returns:
        The events and the cursor for the next page, or None on the last page.

    Raises:
        ValueError: If the cursor or group is malformed, the outcome is unknown, or the
            weekday and hour are not both given and in range.
    """
    _check_slot(weekday, hour)
    limit = max(1, min(limit, _MAX_PAGE))
    where, params = _where(filters)
    if weekday is not None and hour is not None:
        # One JSON parameter, since a long range holds more buckets than SQLite allows as
        # bound variables or OR terms.
        buckets = _hour_buckets(conn, filters, weekday, hour)
        where = _and(where, _BUCKET + " IN (SELECT value FROM json_each(?))")  # noqa: S608
        params = [*params, json.dumps(buckets)]
    if gate is not None:
        where = _and(where, "repo IS ? AND name = ?")
        params = [*params, gate[0], gate[1]]
    prefix, prefix_params = "", []
    if flaky:
        # Flakiness is decided over every outcome in the window, whatever else is filtered.
        tree_where, prefix_params = (
            _where(filters, name=gate[1], exact_repo=(gate[0],)) if gate else _where(filters)
        )
        prefix = _flaky_trees_cte(tree_where)
        where = _and(where, _ON_FLAKY_TREE)
    if outcome is not None:
        if outcome not in _OUTCOMES:
            msg = f"unknown outcome: {outcome!r}"
            raise ValueError(msg)
        where = _and(where, "outcome = ?")
        params = [*params, outcome]
    if reason is not None:
        where = _and(where, "reason = ?")
        params = [*params, reason]
    if group is not None:
        condition, values = group_filter(by=group[0], key=group[1])
        where = _and(where, condition)
        params = [*params, *values]
    if before is not None:
        ts, event_id = _parse_cursor(before)
        where = _and(where, "(ts < ? OR (ts = ? AND id < ?))")
        params = [*params, ts, ts, event_id]
    names = _all_repo_names(conn)
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


def flaky(conn: sqlite3.Connection, filters: Filters) -> dict[str, Any]:
    """Return gates with trees that both failed and passed, newest first."""
    where, params = _where(filters)
    names = _all_repo_names(conn)
    runs: dict[tuple[str | None, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in conn.execute(
        f"{_flaky_trees_cte(where)}SELECT {_ROW_COLUMNS} FROM events"  # noqa: S608
        + _and(where, _ON_FLAKY_TREE)
        + " ORDER BY ts, id",
        [*params, *params],
    ):
        runs[row[1], row[2], row[8]].append(_event_row(row, names))
    last_seen = {key: max(run["ts"] for run in tree_runs) for key, tree_runs in runs.items()}
    by_gate: dict[tuple[str | None, str], list[tuple[str, float]]] = {}
    for repo, name, tree in sorted(last_seen, key=lambda k: (-last_seen[k], k[2])):
        by_gate.setdefault((repo, name), []).append((tree, last_seen[repo, name, tree]))
    out: list[dict[str, Any]] = [
        {
            "repo": repo,
            "repo_name": names[repo],
            "name": name,
            "tree_count": len(gate_trees),
            "last_seen": max(last for _, last in gate_trees),
            "trees": [{"tree": tree, "runs": runs[repo, name, tree]} for tree, _ in gate_trees],
        }
        for (repo, name), gate_trees in by_gate.items()
    ]
    out.sort(key=lambda g: -g["last_seen"])
    return {"gates": out}
