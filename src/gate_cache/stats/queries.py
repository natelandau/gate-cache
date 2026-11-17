"""Compute the dashboard metrics from the archive."""

from __future__ import annotations

import math
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, get_args
from zoneinfo import ZoneInfo

from gate_cache.stats.recorder import Outcome

if TYPE_CHECKING:
    import sqlite3

_RAN = "('skip', 'pass', 'pass_unrecorded', 'fail')"
_GOOD = "('pass', 'pass_unrecorded')"
_RECENT_LIMIT = 50
_MAX_PAGE = 500
_OUTCOMES: frozenset[str] = frozenset(get_args(Outcome))
# The archive keeps outcomes from newer gate-cache versions; only known ones count.
_KNOWN = "outcome IN (" + ", ".join(f"'{o}'" for o in sorted(_OUTCOMES)) + ")"
_ROW_COLUMNS = "ts, repo, name, outcome, duration, saved, exit_code, reason, tree"
# Every real UTC offset is a whole number of quarter hours, so no bucket spans two local days.
_BUCKET_SECONDS = 900
# Floor division: CAST truncates toward zero, which is one bucket too high for negative ts.
_BUCKET = (
    f"(CAST(ts / {_BUCKET_SECONDS} AS INTEGER)"
    f" - (ts < CAST(ts / {_BUCKET_SECONDS} AS INTEGER) * {_BUCKET_SECONDS}))"
)
_INTEGER_RE = re.compile(r"-?[0-9]+")

# Plain decimal text, optionally in the exponent form repr gives very large or small floats.
NUMBER_RE = re.compile(r"-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?")


@dataclass(frozen=True)
class Filters:
    """Restrict queries to a repo and a half-open time range.

    Attributes:
        repo: Git common directory to match, or None for every repo.
        start: Inclusive lower bound as Unix seconds.
        end: Exclusive upper bound as Unix seconds.
        tz: IANA time zone name used to bucket days.
    """

    repo: str | None = None
    start: float | None = None
    end: float | None = None
    tz: str = "UTC"


def repo_name(repo: str | None) -> str:
    """Return a display name for a git common directory."""
    if repo is None:
        return "unknown repo"
    path = Path(repo)
    return path.parent.name if path.name == ".git" else path.name


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
    elif filters.repo is not None:
        clauses.append("repo = ?")
        params.append(filters.repo)
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


def _flaky_trees(
    conn: sqlite3.Connection, where: str, params: list[Any]
) -> list[tuple[str | None, str, str, int, int, float]]:
    """Return (repo, name, tree, fails, passes, last) for trees with a fail and a pass."""
    sql = (
        "SELECT repo, name, tree,"  # noqa: S608
        " SUM(outcome = 'fail'), SUM(outcome IN " + _GOOD + "), MAX(ts)"
        " FROM events" + _and(where, "tree IS NOT NULL") + " GROUP BY repo, name, tree"
        " HAVING SUM(outcome = 'fail') > 0 AND SUM(outcome IN " + _GOOD + ") > 0"
        " ORDER BY MAX(ts) DESC, tree"
    )
    return [(r[0], r[1], r[2], r[3], r[4], r[5]) for r in conn.execute(sql, params)]


def _event_row(raw: tuple[Any, ...]) -> dict[str, Any]:
    """Convert a row selected with _ROW_COLUMNS into an API dict."""
    ts, repo, name, outcome, duration, saved, exit_code, reason, tree = raw
    return {
        "ts": ts,
        "repo": repo,
        "repo_name": repo_name(repo),
        "name": name,
        "outcome": outcome,
        "duration": duration,
        "saved": saved,
        "exit_code": exit_code,
        "reason": reason,
        "tree": tree,
    }


def summary(conn: sqlite3.Connection, filters: Filters) -> dict[str, Any]:
    """Return headline totals and per-day buckets.

    Args:
        conn: Archive connection.
        filters: Repo and range filters.

    Returns:
        Totals, with runs counting every recorded event including uncached ones.
    """
    zone = _zone(filters.tz)
    where, params = _where(filters)
    row = conn.execute(
        "SELECT COUNT(*),"  # noqa: S608
        " COALESCE(SUM(outcome = 'skip'), 0),"
        " COALESCE(SUM(outcome IN " + _RAN + "), 0),"
        " COALESCE(SUM(outcome = 'uncached'), 0),"
        " COALESCE(SUM(outcome = 'fail'), 0),"
        " COALESCE(SUM(CASE WHEN outcome = 'skip' THEN saved END), 0.0),"
        " COALESCE(SUM(outcome = 'skip' AND saved IS NULL), 0)"
        " FROM events" + where,
        params,
    ).fetchone()
    runs, skips, ran, uncached, failures, saved, unknown = row
    buckets: dict[str, list[float]] = defaultdict(lambda: [0.0, 0, 0])
    for bucket_id, bucket_saved, bucket_failures, bucket_runs in conn.execute(
        "SELECT " + _BUCKET + ","  # noqa: S608
        " COALESCE(SUM(CASE WHEN outcome = 'skip' THEN saved END), 0.0),"
        " SUM(outcome = 'fail'), COUNT(*)"
        " FROM events" + where + " GROUP BY 1",
        params,
    ):
        start = datetime.fromtimestamp(bucket_id * _BUCKET_SECONDS, tz=UTC)
        bucket = buckets[start.astimezone(zone).date().isoformat()]
        bucket[0] += bucket_saved
        bucket[1] += bucket_failures
        bucket[2] += bucket_runs
    return {
        "time_saved": float(saved),
        "unknown_saved_skips": unknown,
        "runs": runs,
        "skips": skips,
        "skip_rate": _skip_rate(skips, ran),
        "uncached": uncached,
        "failures": failures,
        "flaky_gates": len({(r[0], r[1]) for r in _flaky_trees(conn, where, params)}),
        "daily": [
            {"day": day, "saved": float(b[0]), "failures": int(b[1]), "runs": int(b[2])}
            for day, b in sorted(buckets.items())
        ],
    }


def gates(conn: sqlite3.Connection, filters: Filters) -> dict[str, Any]:
    """Return per-gate metrics ordered by time saved."""
    where, params = _where(filters)
    flaky_keys = {(r[0], r[1]) for r in _flaky_trees(conn, where, params)}
    durations: dict[tuple[str | None, str], list[float]] = {}
    for repo, name, duration in conn.execute(
        "SELECT repo, name, duration FROM events"  # noqa: S608
        + _and(where, "outcome = 'pass' AND duration IS NOT NULL"),
        params,
    ):
        durations.setdefault((repo, name), []).append(duration)
    rows = conn.execute(
        "SELECT repo, name, COUNT(*),"  # noqa: S608
        " SUM(outcome = 'skip'), SUM(outcome IN " + _RAN + "),"
        " COALESCE(SUM(CASE WHEN outcome = 'skip' THEN saved END), 0.0),"
        " SUM(outcome = 'fail'), MAX(ts)"
        " FROM events" + where + " GROUP BY repo, name",
        params,
    ).fetchall()
    out: list[dict[str, Any]] = []
    for repo, name, runs, skips, ran, saved, failures, last in rows:
        durs = durations.get((repo, name), [])
        out.append(
            {
                "repo": repo,
                "repo_name": repo_name(repo),
                "name": name,
                "runs": runs,
                "skip_rate": _skip_rate(skips, ran),
                "avg_run": statistics.fmean(durs) if durs else None,
                "median_run": float(statistics.median(durs)) if durs else None,
                "time_saved": float(saved),
                "failures": failures,
                "last_run": last,
                "flaky": (repo, name) in flaky_keys,
            }
        )
    out.sort(key=lambda g: (-g["time_saved"], g["repo_name"], g["name"]))
    return {"gates": out}


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
    return {
        "repo": repo,
        "repo_name": repo_name(repo),
        "name": name,
        "trend": [{"ts": ts, "duration": d} for ts, d in trend],
        "recent": [_event_row(r) for r in recent],
        "flaky_trees": [
            {"tree": tree, "fails": fails, "passes": passes, "last": last}
            for _, _, tree, fails, passes, last in _flaky_trees(conn, where, params)
        ],
    }


def repos(conn: sqlite3.Connection, filters: Filters) -> dict[str, Any]:
    """Return per-repo rollups ordered by time saved."""
    where, params = _where(filters)
    rows = conn.execute(
        "SELECT repo, COUNT(*), SUM(outcome = 'skip'), SUM(outcome IN " + _RAN + "),"  # noqa: S608
        " COALESCE(SUM(CASE WHEN outcome = 'skip' THEN saved END), 0.0),"
        " SUM(outcome = 'fail'), COUNT(DISTINCT name)"
        " FROM events" + where + " GROUP BY repo",
        params,
    ).fetchall()
    out: list[dict[str, Any]] = [
        {
            "repo": repo,
            "repo_name": repo_name(repo),
            "runs": runs,
            "skip_rate": _skip_rate(skips, ran),
            "time_saved": float(saved),
            "failures": failures,
            "gates": n_gates,
        }
        for repo, runs, skips, ran, saved, failures, n_gates in rows
    ]
    out.sort(key=lambda r: (-r["time_saved"], r["repo_name"]))
    return {"repos": out}


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


def activity(
    conn: sqlite3.Connection,
    filters: Filters,
    *,
    limit: int = 100,
    before: str | None = None,
    outcome: str | None = None,
) -> dict[str, Any]:
    """Return one page of events, newest first.

    Args:
        conn: Archive connection.
        filters: Repo and range filters.
        limit: Page size, clamped to 1..500.
        before: Opaque cursor from a previous page's next_before.
        outcome: Keep only events with this outcome, or every event when None.

    Returns:
        The events and the cursor for the next page, or None on the last page.

    Raises:
        ValueError: If the cursor is malformed or the outcome is unknown.
    """
    limit = max(1, min(limit, _MAX_PAGE))
    where, params = _where(filters)
    if outcome is not None:
        if outcome not in _OUTCOMES:
            msg = f"unknown outcome: {outcome!r}"
            raise ValueError(msg)
        where = _and(where, "outcome = ?")
        params = [*params, outcome]
    if before is not None:
        ts, event_id = _parse_cursor(before)
        where = _and(where, "(ts < ? OR (ts = ? AND id < ?))")
        params = [*params, ts, ts, event_id]
    rows = conn.execute(
        f"SELECT {_ROW_COLUMNS}, id FROM events{where} ORDER BY ts DESC, id DESC LIMIT ?",  # noqa: S608
        [*params, limit + 1],
    ).fetchall()
    page = rows[:limit]
    more = len(rows) > limit
    return {
        "events": [_event_row(r[:-1]) for r in page],
        "next_before": f"{page[-1][0]!r}:{page[-1][-1]}" if more else None,
    }


def flaky(conn: sqlite3.Connection, filters: Filters) -> dict[str, Any]:
    """Return gates with trees that both failed and passed, newest first."""
    where, params = _where(filters)
    runs: dict[tuple[str | None, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in conn.execute(
        "WITH f AS (SELECT repo AS frepo, name AS fname, tree AS ftree FROM events"  # noqa: S608
        + _and(where, "tree IS NOT NULL")
        + " GROUP BY repo, name, tree"
        " HAVING SUM(outcome = 'fail') > 0 AND SUM(outcome IN " + _GOOD + ") > 0)"  # noqa: S608
        f" SELECT {_ROW_COLUMNS} FROM events JOIN f"
        " ON events.repo IS f.frepo AND events.name = f.fname AND events.tree = f.ftree"
        + where
        + " ORDER BY ts, id",
        [*params, *params],
    ):
        runs[row[1], row[2], row[8]].append(_event_row(row))
    last_seen = {key: max(run["ts"] for run in tree_runs) for key, tree_runs in runs.items()}
    by_gate: dict[tuple[str | None, str], list[tuple[str, float]]] = {}
    for repo, name, tree in sorted(last_seen, key=lambda k: (-last_seen[k], k[2])):
        by_gate.setdefault((repo, name), []).append((tree, last_seen[repo, name, tree]))
    out: list[dict[str, Any]] = [
        {
            "repo": repo,
            "repo_name": repo_name(repo),
            "name": name,
            "tree_count": len(gate_trees),
            "last_seen": max(last for _, last in gate_trees),
            "trees": [{"tree": tree, "runs": runs[repo, name, tree]} for tree, _ in gate_trees],
        }
        for (repo, name), gate_trees in by_gate.items()
    ]
    out.sort(key=lambda g: -g["last_seen"])
    return {"gates": out}
