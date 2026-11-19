"""Tests for the activity feed's gate and flaky filters."""

import json
import sqlite3
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from gate_cache.stats.archive import Archive
from gate_cache.stats.queries import Filters, activity

NEW_YORK = ZoneInfo("America/New_York")
REPO_A = "/x/a/.git"
REPO_B = "/x/b/.git"


def insert(
    conn: sqlite3.Connection,
    ts: float,
    outcome: str = "pass",
    *,
    repo: str | None = REPO_A,
    name: str = "lint",
    tree: str | None = "t1",
) -> None:
    """Insert one event row."""
    conn.execute(
        "INSERT INTO events (line_hash, ts, repo, name, tree, paths, outcome)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (f"h{conn.total_changes}-{ts}-{name}", ts, repo, name, tree, json.dumps([]), outcome),
    )
    conn.commit()


def local(*parts: int) -> float:
    """Return Unix seconds for a New York wall-clock time."""
    return datetime(*parts, tzinfo=NEW_YORK).timestamp()


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Provide the connection of an empty archive."""
    with Archive.open(tmp_path / "a.sqlite3") as arch:
        yield arch.connection


def stamps(page: dict) -> list[float]:
    """Return the timestamps of a page's events."""
    return [event["ts"] for event in page["events"]]


def test_gate_filter(conn: sqlite3.Connection) -> None:
    """Verify each gate matches one name in one repo, including the unknown repo, and gates OR."""
    insert(conn, 1.0)
    insert(conn, 2.0, name="test")
    insert(conn, 3.0, repo=REPO_B)
    insert(conn, 4.0, repo=None)
    insert(conn, 5.0, "fail", repo=None)
    insert(conn, 6.0, "pass", repo=None)

    assert stamps(activity(conn, Filters(), gates=[(REPO_A, "lint")])) == [1.0]
    assert stamps(activity(conn, Filters(), gates=[(None, "lint")])) == [6.0, 5.0, 4.0]
    both = [(REPO_A, "lint"), (REPO_B, "lint")]
    assert stamps(activity(conn, Filters(), gates=both)) == [3.0, 1.0]
    # AND across dimensions: the gates, then their failures, then their flaky runs.
    unknown_or_a = [(None, "lint"), (REPO_A, "lint")]
    assert stamps(activity(conn, Filters(), gates=unknown_or_a, outcomes=["fail"])) == [5.0]
    assert stamps(activity(conn, Filters(), gates=unknown_or_a, flaky=True)) == [6.0, 5.0, 4.0]


@pytest.mark.parametrize("repo", [REPO_A, None])
def test_flaky_filter_returns_runs_on_flaky_trees(
    conn: sqlite3.Connection, repo: str | None
) -> None:
    """Verify only runs on trees that both failed and passed are returned."""
    insert(conn, 1.0, "fail", repo=repo)
    insert(conn, 2.0, "pass", repo=repo)
    insert(conn, 3.0, "skip", repo=repo)
    insert(conn, 4.0, "pass", repo=repo, tree="t2")
    insert(conn, 5.0, "fail", repo=REPO_B)

    assert stamps(activity(conn, Filters(), flaky=True)) == [3.0, 2.0, 1.0]


def test_flaky_filter_uses_window_not_other_filters(conn: sqlite3.Connection) -> None:
    """Verify flakiness is decided over every outcome in the window."""
    insert(conn, 1.0, "fail")
    insert(conn, 2.0, "pass")

    assert stamps(activity(conn, Filters(), flaky=True, outcomes=["fail"])) == [1.0]
    assert stamps(activity(conn, Filters(start=1.5), flaky=True)) == []


def test_flaky_filter_scales_with_archive_size(conn: sqlite3.Connection) -> None:
    """Verify the flaky filter decides flaky trees once, not once per event."""
    rows = [
        (
            f"h{i}",
            float(i),
            REPO_A,
            "abc"[i % 7000 % 3],
            f"t{i % 7000}",
            "[]",
            ("pass", "fail", "skip")[i // 7000],
        )
        for i in range(20_000)
    ]
    conn.executemany(
        "INSERT INTO events (line_hash, ts, repo, name, tree, paths, outcome) VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()

    started = time.perf_counter()
    page = activity(conn, Filters(), flaky=True)

    assert time.perf_counter() - started < 1.0
    assert page["events"]
