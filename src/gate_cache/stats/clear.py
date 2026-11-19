"""Delete the recorded stats of one repository, or of every repository on this machine."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from gate_cache.stats import config
from gate_cache.stats.archive import (
    ARCHIVE_NAME,
    Archive,
    ArchiveVersionError,
    archive_path,
    has_records,
)
from gate_cache.stats.context import MACHINE_ID_TEMP_GLOB
from gate_cache.stats.junit import TESTS_DIR_NAME
from gate_cache.stats.lock import InstanceLock
from gate_cache.stats.recorder import INBOX_NAME

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_SUMMARY = (
    "SELECT count(*), count(DISTINCT gate), count(DISTINCT repo), min(ts), max(ts) FROM events"
)


class StatsInUseError(Exception):
    """The dashboard or a stats report holds the stats, so they cannot be cleared."""


@dataclass(frozen=True)
class StatsSummary:
    """What a clear of the stats covers, so a person can judge it before typing yes.

    Attributes:
        repo: The repo's git common directory, or None for every repo.
        label: The repo's display name, or None for every repo.
        runs: Recorded runs, or None when the archive cannot be read.
        gates: Gates with recorded runs.
        repos: Repos with recorded runs.
        first: Unix time of the oldest run, or None when there is none.
        last: Unix time of the newest run, or None when there is none.
    """

    repo: str | None
    label: str | None = None
    runs: int | None = 0
    gates: int = 0
    repos: int = 0
    first: float | None = None
    last: float | None = None


@dataclass(frozen=True)
class ClearResult:
    """The summary a clear showed, and whether it deleted the stats."""

    summary: StatsSummary
    deleted: bool


def _summarize(conn: sqlite3.Connection, repo: str | None) -> StatsSummary:
    """Count the runs, gates, and repos of one repo, or of all when repo is None."""
    from gate_cache.stats import queries

    where = "" if repo is None else " WHERE repo = ?"
    runs, gates, repos, first, last = conn.execute(
        _SUMMARY + where, () if repo is None else (repo,)
    ).fetchone()
    label = None if repo is None else queries.all_repo_names(conn)[repo]
    return StatsSummary(
        repo=repo, label=label, runs=runs, gates=gates, repos=repos, first=first, last=last
    )


def clear_stats(
    *,
    repo: str | None,
    decide: Callable[[StatsSummary], bool],
    resolve: Callable[[sqlite3.Connection | None], str] | None = None,
) -> ClearResult:
    """Delete the recorded runs of one repo, or every stats file when repo is None.

    Pending runs are moved into the archive first, so the summary counts them and a repo's
    clear deletes them. Ask `decide` before deleting, since the deletion cannot be undone.
    Clearing every repo keeps `machine-id` so the machine keeps its ID, but removes temp
    files a killed run left while it created that file.

    Args:
        repo: The git common directory of the repo to clear, or None for every repo.
        decide: Called with the summary while the stats are locked; returns True to delete.
            It never runs when one repo has no runs to delete. Every repo's files are
            offered even with no runs, since leftover files can stay.
        resolve: Finds the repo to clear in the open archive, or in None when nothing was
            recorded, such as from a `--repo` name. It replaces `repo` when given.

    Returns:
        The summary, and whether the stats were deleted.

    Raises:
        StatsInUseError: When the dashboard or a report holds the stats.
        OSError: When the lock or a file cannot be handled.
        sqlite3.Error: When one repo's runs cannot be read or deleted.
        ArchiveVersionError: When a newer gate-cache wrote the archive and one repo is cleared.
    """
    state = config.state_dir()
    lock = InstanceLock.acquire(state)
    if lock is None:
        message = "stats are in use by the dashboard or a stats report"
        raise StatsInUseError(message)
    try:
        if resolve is not None:
            return _clear_repo(state, resolve=resolve, decide=decide)
        if repo is not None:
            return _clear_repo(state, resolve=lambda _conn: repo, decide=decide)
        return _clear_all(state, decide=decide)
    finally:
        lock.release()


def _clear_repo(
    state: Path,
    *,
    resolve: Callable[[sqlite3.Connection | None], str],
    decide: Callable[[StatsSummary], bool],
) -> ClearResult:
    if not has_records():
        return ClearResult(StatsSummary(repo=resolve(None)), deleted=False)
    with Archive.open(archive_path()) as archive:
        archive.ingest(state / INBOX_NAME, fresh=True)
        repo = resolve(archive.connection)
        summary = _summarize(archive.connection, repo)
        if not summary.runs or not decide(summary):
            return ClearResult(summary, deleted=False)
        archive.forget_repo(repo, inbox=state / INBOX_NAME)
    return ClearResult(summary, deleted=True)


def _clear_all(state: Path, *, decide: Callable[[StatsSummary], bool]) -> ClearResult:
    summary = StatsSummary(repo=None)
    if has_records():
        try:
            with Archive.open(archive_path()) as archive:
                archive.ingest(state / INBOX_NAME, fresh=True)
                summary = _summarize(archive.connection, None)
        except (sqlite3.Error, ArchiveVersionError):
            # The files can still be deleted when the archive cannot be read.
            summary = replace(summary, runs=None)
    if not decide(summary):
        return ClearResult(summary, deleted=False)
    targets = [
        state / INBOX_NAME,
        *state.glob("events.*.processing"),
        *state.glob(MACHINE_ID_TEMP_GLOB),
        *(state / f"{ARCHIVE_NAME}{suffix}" for suffix in ("", "-wal", "-shm")),
        # The folder stays, since a gate run can write into it meanwhile.
        *(state / TESTS_DIR_NAME).glob("*"),
    ]
    for target in targets:
        target.unlink(missing_ok=True)
    return ClearResult(summary, deleted=True)
