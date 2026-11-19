"""Build the `stats report` JSON contract from the recorded gate runs.

Every number comes from `queries`; this module only maps query results into a versioned
shape, so dashboard shapes can change without breaking the report.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gate_cache.markers import utc_timestamp
from gate_cache.snapshot import git_common_dir
from gate_cache.stats import config, queries
from gate_cache.stats.archive import Archive, archive_path, tests_since
from gate_cache.stats.lock import InstanceLock
from gate_cache.stats.queries import Filters
from gate_cache.stats.recorder import INBOX_NAME
from gate_cache.stats.window import bucket_for

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable, Generator, Sequence
    from zoneinfo import ZoneInfo

    CurrentStatus = Callable[[str, Sequence[str]], dict[str, Any] | None]

REPORT_SCHEMA = 1

_ZERO_TOTALS: dict[str, float] = dict.fromkeys(
    ("runs", "skips", *queries.SPOT_CHECK_KEYS), 0
) | dict.fromkeys(("time_saved", "time_spent", "fail_time", "overhead"), 0.0)


class RepoNotFoundError(LookupError):
    """No recorded repo matches the requested name or path."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


class AmbiguousRepoError(LookupError):
    """Several recorded repos match the requested name.

    Attributes:
        text: The name as given.
        matches: Each matching repo as (display name, work tree path).
    """

    def __init__(self, text: str, matches: list[tuple[str, str]]) -> None:
        super().__init__(text)
        self.text = text
        self.matches = matches


@dataclass(frozen=True)
class Window:
    """The half-open time range a report covers, and the zone its trend buckets use.

    Attributes:
        ends_now: Whether the range runs up to the moment of the report, so text can call
            it the last N days.
    """

    start: float
    end: float
    tz: ZoneInfo
    ends_now: bool = True

    @property
    def days(self) -> float:
        """Length of the window in days."""
        return (self.end - self.start) / 86400

    def to_json(self) -> dict[str, Any]:
        """Return the window as the contract's `window` object."""
        return {"since": iso(self.start), "until": iso(self.end), "days": round(self.days, 4)}

    def filters(self, repos: tuple[str | None, ...] | None) -> Filters:
        """Return query filters for this window over `repos`, every repo when None."""
        return Filters(repos=repos or (), start=self.start, end=self.end, tz=self.tz.key)


def iso(ts: float | None) -> str | None:
    """Format Unix seconds as ISO 8601 UTC with seconds precision and a `Z` suffix."""
    return None if ts is None else utc_timestamp(ts)


@contextmanager
def open_record() -> Generator[sqlite3.Connection | None]:
    """Open the stats archive with pending events ingested, for reading a report.

    Ingest happens only under the stats instance lock. When another process holds it, such
    as a running dashboard, which ingests on its own, the archive is read as it is.

    Yields:
        The archive connection, or None when nothing was ever recorded.
    """
    state = config.state_dir()
    path = archive_path()
    inbox = state / INBOX_NAME
    if not path.exists() and not inbox.exists():
        yield None
        return
    try:
        lock = InstanceLock.acquire(state)
    except OSError:
        # A state directory the lock cannot use can still be read.
        lock = None
    try:
        with Archive.open(path) as archive:
            if lock is not None:
                archive.ingest(inbox, fresh=True)
                # Free the lock before the report renders, so a dashboard can start meanwhile.
                lock.release()
                lock = None
            yield archive.connection
    finally:
        if lock is not None:
            lock.release()


def resolve_repo(conn: sqlite3.Connection, text: str) -> str:
    """Turn a `--repo` value, a path or a name, into a recorded repo's git common directory.

    A path inside a recorded repo wins. Otherwise the text must equal one repo's display
    name or work tree folder name.

    Raises:
        RepoNotFoundError: When no recorded repo matches.
        AmbiguousRepoError: When several recorded repos match the name.
    """
    names = queries.all_repo_names(conn)
    path = Path(text)
    if path.is_file():
        path = path.parent
    if path.is_dir():
        common = git_common_dir(path)
        if common is not None and str(common) in names:
            return str(common)
    matches = sorted(
        (label, str(queries.work_dir(repo)), repo)
        for repo, label in names.items()
        if repo is not None and text in {label, queries.work_dir(repo).name}
    )
    if not matches:
        raise RepoNotFoundError(text)
    if len(matches) > 1:
        raise AmbiguousRepoError(text, [(label, folder) for label, folder, _ in matches])
    return matches[0][2]


def _capped(total: int, items: list[Any]) -> dict[str, Any]:
    return {"total": total, "shown": len(items), "items": items}


def _capped_list(items: list[Any], limit: int) -> dict[str, Any]:
    return _capped(len(items), items[:limit])


def _flaky_note(counts: dict[str, Any] | None) -> dict[str, Any] | None:
    if counts is None:
        return None
    return {**counts, "last_seen": iso(counts["last_seen"])}


def _spot_checks(counts: dict[str, Any], **extra: Any) -> dict[str, Any] | None:
    """Map a gate's spot-check counts into the contract, or None when no spot check ran."""
    if not counts["spot_checks"]:
        return None
    return {"run": counts["spot_checks"], "failed": counts["spot_check_failures"], **extra}


def _suite_gates(
    conn: sqlite3.Connection, filters: Filters, *, with_repo: bool, since: float
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return the per-gate rows of the suite view and the totals they add up to."""
    rows = queries.gate_rows(conn, filters)
    flaky = queries.gate_flaky_counts(conn, filters)
    uncached = queries.gate_uncached(conn, filters)
    waits = queries.gate_waits(conn, filters)
    overhead = queries.gate_overhead(conn, filters)
    commands = queries.gate_latest_command(conn, filters)
    tests = queries.gate_test_counts(conn, filters, since=since)
    # The dashboard's top-5 cut would hide a slowdown on any other gate.
    slow = {
        (g["repo"], g["name"]): {k: g[k] for k in ("before", "now", "change")}
        for g in queries.slowdowns(conn, filters, limit=len(rows))["gates"]
    }
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (row["repo"], row["name"])
        command, paths = commands[key]
        out.append(
            {
                **({"repo": row["repo"], "repo_name": row["repo_name"]} if with_repo else {}),
                "name": row["name"],
                "command": command,
                "paths": paths,
                **{k: row[k] for k in queries.SUMMARY_KEYS},
                "last_run": iso(row["last_run"]),
                "flaky": _flaky_note(flaky.get(key)),
                "slowdown": slow.get(key),
                "uncached": uncached.get(key, []),
                "waits": waits.get(key),
                "tests": tests.get(key),
                "spot_checks": _spot_checks(
                    row, last_failed=iso(row[queries.LAST_FAILED_SPOT_CHECK])
                ),
            }
        )
    out.sort(key=lambda g: (-g["time_spent"], g["name"], g.get("repo_name", "")))
    totals = {key: sum(r[key] for r in rows) for key in _ZERO_TOTALS if key != "overhead"}
    totals["overhead"] = sum(overhead.values())
    return out, totals


def suite_report(
    conn: sqlite3.Connection | None,
    *,
    repos: tuple[str | None, ...] | None,
    window: Window,
    recording: bool,
    now: float | None = None,
) -> dict[str, Any]:
    """Build the suite view: one row per gate, most time spent first.

    Args:
        conn: Archive connection, or None when nothing was ever recorded.
        repos: Repos to cover; None covers every repo and names the repo on each gate.
        window: Time range of the report.
        recording: Whether stats recording is on; when off, the report says so.
        now: Current Unix time in seconds, where per-test retention counts back from;
            defaults to the clock.

    Returns:
        The suite view of the report contract.
    """
    match repos:
        case (single,):
            names = queries.repo_names([single]) if conn is None else queries.all_repo_names(conn)
            repo_name: str | None = names[single]
        case _:
            single = repo_name = None
    gate_rows: list[dict[str, Any]] = []
    totals = dict(_ZERO_TOTALS)
    if conn is not None:
        gate_rows, totals = _suite_gates(
            conn, window.filters(repos), with_repo=repo_name is None, since=_tests_since(now)
        )
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "repo": single,
        "repo_name": repo_name,
        "window": window.to_json(),
        "totals": totals,
        "gates": gate_rows,
    }
    if not recording:
        report["recording"] = False
    return report


def _tests_since(now: float | None) -> float:
    return tests_since(time.time() if now is None else now)


def _run_items(
    rows: list[dict[str, Any]], failed: dict[int, tuple[int, list[str]]]
) -> list[dict[str, Any]]:
    return [
        {
            **{key: value for key, value in row.items() if key != "id"},
            "ts": iso(row["ts"]),
            "failed_tests": _capped(*failed[row["id"]]) if row["id"] in failed else None,
        }
        for row in rows
    ]


def _test_detail(tests: dict[str, Any] | None, limit: int) -> dict[str, Any] | None:
    """Map a gate's per-test detail into the contract, each list capped at `limit`."""
    if tests is None:
        return None
    flaky = [
        {"name": t["name"], "fails": t["fails"], "passes": t["passes"], "last_seen": iso(t["last"])}
        for t in tests["flaky"]
    ]
    retried = [
        {"name": t["name"], "runs": t["runs"], "last_seen": iso(t["last"])}
        for t in tests["retried"]
    ]
    return {
        "since": iso(tests["since"]),
        "slowest": _capped_list(tests["slowest"], limit),
        "flaky": _capped_list(flaky, limit),
        "retried": _capped_list(retried, limit),
        "report_problems": tests["report_problems"],
    }


def gate_report(  # noqa: PLR0913
    conn: sqlite3.Connection,
    *,
    repo: str | None,
    name: str,
    window: Window,
    limit: int,
    current: CurrentStatus | None,
    recording: bool,
    now: float | None = None,
) -> dict[str, Any] | None:
    """Build the one-gate view: what the gate costs, how it fails, and its recent runs.

    Args:
        conn: Archive connection.
        repo: The gate's repo.
        name: Gate, the name before any `@` key.
        window: Time range of the report.
        limit: Most items any capped list shows.
        current: Looks up a gate name's status on the current content; None when the repo
            is not the current one.
        recording: Whether stats recording is on; when off, the report says so.
        now: Current Unix time in seconds, where per-test retention counts back from;
            defaults to the clock.

    Returns:
        The one-gate view, or None when the repo never recorded the gate.
    """
    # Over the whole record, so a gate with no runs in the window still shows its command.
    found = queries.gate_command(conn, repo=repo, name=name)
    if found is None:
        return None
    command, paths = found
    filters = window.filters((repo,))
    all_variants = queries.gate_variants(conn, filters, repo=repo, name=name)
    in_window = [v for v in all_variants if v["runs"]]
    variants = [
        {
            "name": v["name"],
            "runs": v["runs"],
            "last_run": iso(v["last_run"]),
            "current": current(v["name"], v["paths"]) if current else None,
        }
        for v in in_window[:limit]
    ]
    # A pass is recorded per variant, so a keyed gate has no single status, even when its
    # keyed runs all fall outside the window.
    keyed = bool(all_variants)
    top_current = current(name, paths) if current and not keyed else None
    trees = queries.gate_flaky_trees(conn, filters, repo=repo, name=name)
    tree_runs = [
        queries.gate_runs(conn, filters, repo=repo, name=name, limit=limit, tree=tree["tree"])
        for tree in trees[:limit]
    ]
    recent_total, recent = queries.gate_runs(conn, filters, repo=repo, name=name, limit=limit)
    summary = queries.gate_summary(conn, filters, repo=repo, name=name)
    spot_counts = {key: summary.pop(key) for key in queries.SPOT_CHECK_KEYS}
    spot_failed_total, spot_failed = (
        queries.gate_runs(conn, filters, repo=repo, name=name, limit=limit, failed_spot_checks=True)
        if spot_counts["spot_check_failures"]
        else (0, [])
    )
    failed = queries.failed_tests(
        conn,
        [
            run["id"]
            for runs in [recent, spot_failed, *(runs for _, runs in tree_runs)]
            for run in runs
            if run["outcome"] == "fail"
        ],
    )
    flaky_trees = [
        {
            "tree": tree["tree"],
            "fails": tree["fails"],
            "passes": tree["passes"],
            "last_seen": iso(tree["last"]),
            "runs": _capped(runs_total, _run_items(runs, failed)),
        }
        for tree, (runs_total, runs) in zip(trees[:limit], tree_runs, strict=True)
    ]
    gate_key = (repo, name)
    bucket = bucket_for(window.days)
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "repo": repo,
        "repo_name": queries.all_repo_names(conn)[repo],
        "name": name,
        "command": command,
        "paths": paths,
        "variants": _capped(len(in_window), variants),
        "window": window.to_json(),
        "keyed": keyed,
        "current": top_current,
        "summary": summary,
        "trend": {
            "bucket": bucket,
            "items": queries.gate_trend(
                conn, filters, repo=repo, name=name, bucket=bucket, tz=window.tz
            ),
        },
        "failure_timing": queries.gate_failure_timing(conn, filters, repo=repo, name=name),
        "exit_codes": queries.gate_exit_codes(conn, filters, repo=repo, name=name),
        **{
            key: _capped_list(rows, limit)
            for key, rows in queries.gate_dimensions(conn, filters, repo=repo, name=name).items()
        },
        "uncached": queries.gate_uncached(conn, filters, gate_key=gate_key).get(gate_key, []),
        "waits": queries.gate_waits(conn, filters, gate_key=gate_key).get(gate_key),
        "flaky_trees": _capped(len(trees), flaky_trees),
        "recent": _capped(recent_total, _run_items(recent, failed)),
        "spot_checks": _spot_checks(
            spot_counts, failures=_capped(spot_failed_total, _run_items(spot_failed, failed))
        ),
        "tests": _test_detail(
            queries.gate_tests(
                conn,
                filters,
                repo=repo,
                name=name,
                since=_tests_since(now),
                gate_median=summary["median_run"],
            ),
            limit=limit,
        ),
    }
    if not recording:
        report["recording"] = False
    return report
