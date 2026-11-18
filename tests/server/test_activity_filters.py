"""Tests for the activity feed's weekday and hour, gate, and flaky filters."""

import json
import sqlite3
import time
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from gate_cache.stats.archive import Archive
from gate_cache.stats.queries import Filters, activity, hourly

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


def test_weekday_hour_keeps_matching_local_hour(conn: sqlite3.Connection) -> None:
    """Verify only events in the local weekday and hour are returned."""
    # 2026-11-10 is a Tuesday.
    tue_1405 = local(2026, 11, 10, 14, 5)
    tue_1459 = local(2026, 11, 10, 14, 59)
    for ts in (tue_1405, tue_1459, local(2026, 11, 10, 15, 0), local(2026, 11, 11, 14, 30)):
        insert(conn, ts)
    filters = Filters(start=local(2026, 11, 1), end=local(2026, 11, 20), tz="America/New_York")

    page = activity(conn, filters, weekday=2, hour=14)

    assert stamps(page) == [tue_1459, tue_1405]


def test_weekday_hour_matches_hourly_across_dst(conn: sqlite3.Connection) -> None:
    """Verify each weekday and hour count equals the heatmap cell across DST changes."""
    start = local(2026, 3, 1)
    for step in range(0, 75 * 86400, 2399):  # an odd step lands on every hour over time
        insert(conn, start + step)
    for day in (local(2026, 3, 8, 1, 30), local(2026, 11, 1, 1, 30)):
        insert(conn, day)
        insert(conn, day + 3600)
    filters = Filters(start=start, end=local(2026, 11, 8), tz="America/New_York")
    cells = hourly(conn, filters)["cells"]

    for cell in cells:
        page = activity(conn, filters, weekday=cell["weekday"], hour=cell["hour"], limit=500)
        assert len(page["events"]) == cell["runs"], (cell["weekday"], cell["hour"])


def test_weekday_hour_without_start_uses_earliest_event(conn: sqlite3.Connection) -> None:
    """Verify an open range still finds old events in the slot."""
    ts = local(2026, 1, 6, 9, 30)  # a Tuesday
    insert(conn, ts)

    page = activity(conn, Filters(tz="America/New_York"), weekday=2, hour=9)

    assert stamps(page) == [ts]


def test_weekday_hour_on_empty_archive(conn: sqlite3.Connection) -> None:
    """Verify an empty archive gives an empty last page."""
    assert activity(conn, Filters(), weekday=0, hour=0) == {"events": [], "next_before": None}


@pytest.mark.parametrize(
    ("weekday", "hour"),
    [(2, None), (None, 3), (7, 3), (-1, 3), (2, 24), (2, -1)],
)
def test_weekday_hour_rejects_bad_values(
    conn: sqlite3.Connection, weekday: int | None, hour: int | None
) -> None:
    """Verify a lone or out-of-range weekday or hour is an error."""
    with pytest.raises(ValueError, match=r"weekday|hour"):
        activity(conn, Filters(), weekday=weekday, hour=hour)


def test_gate_filter(conn: sqlite3.Connection) -> None:
    """Verify the gate filter matches one name in one repo, including the unknown repo."""
    insert(conn, 1.0)
    insert(conn, 2.0, name="test")
    insert(conn, 3.0, repo=REPO_B)
    insert(conn, 4.0, repo=None)

    assert stamps(activity(conn, Filters(), gate=(REPO_A, "lint"))) == [1.0]
    assert stamps(activity(conn, Filters(), gate=(None, "lint"))) == [4.0]


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

    assert stamps(activity(conn, Filters(), flaky=True, outcome="fail")) == [1.0]
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


def test_weekday_hour_bounds_a_huge_window_by_the_archive(conn: sqlite3.Connection) -> None:
    """Verify a window far wider than the archive builds slots only where events exist."""
    ts = local(2026, 11, 10, 14, 5)  # a Tuesday
    insert(conn, ts)

    started = time.perf_counter()
    page = activity(
        conn, Filters(start=-60_000_000_000, end=4e9, tz="America/New_York"), weekday=2, hour=14
    )

    assert time.perf_counter() - started < 1.0
    assert stamps(page) == [ts]


def test_weekday_hour_over_many_weeks(conn: sqlite3.Connection) -> None:
    """Verify a slot that spans more buckets than SQLite allows as OR terms still filters."""
    first = datetime(2005, 1, 4, 9, 30, tzinfo=NEW_YORK)  # a Tuesday
    weeks = 1100
    for week in range(weeks):
        insert(conn, (first + timedelta(weeks=week)).timestamp())
    insert(conn, local(2005, 1, 5, 9, 30))  # a Wednesday
    filters = Filters(tz="America/New_York")

    seen = 0
    before = None
    while True:
        page = activity(conn, filters, weekday=2, hour=9, limit=500, before=before)
        seen += len(page["events"])
        before = page["next_before"]
        if before is None:
            break

    assert seen == weeks
