"""Tests for the dashboard metric queries."""

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import get_args

import pytest

from gate_cache.stats import queries
from gate_cache.stats.archive import Archive
from gate_cache.stats.context import Trigger
from gate_cache.stats.queries import (
    Filters,
    activity,
    coalescing,
    flaky,
    gate_detail,
    gates,
    hourly,
    previous_window,
    reasons,
    repo_names,
    repos,
    slowdowns,
    summary,
)

BASE = 1_699_920_000.0  # midnight UTC
DAY = 86400.0
REPO_A = "/x/proj/.git"
REPO_B = "/x/other/.git"


def insert(
    conn: sqlite3.Connection,
    ts: float,
    outcome: str,
    *,
    repo: str | None = REPO_A,
    name: str = "lint",
    tree: str | None = "t1",
    duration: float | None = None,
    saved: float | None = None,
    reason: str | None = None,
    overhead: float | None = None,
    waited: float | None = None,
    wait_known: bool = False,
    reported: bool = False,
    wait_timed_out: bool = False,
) -> None:
    """Insert one event row."""
    conn.execute(
        "INSERT INTO events (line_hash, ts, repo, name, tree, paths, outcome, duration, saved,"
        " reason, overhead, waited, wait_known, reported, wait_timed_out)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"h{conn.total_changes}-{ts}",
            ts,
            repo,
            name,
            tree,
            json.dumps(["src"]),
            outcome,
            duration,
            saved,
            reason,
            overhead,
            waited,
            wait_known,
            reported,
            wait_timed_out,
        ),
    )
    conn.commit()


@pytest.fixture
def empty_conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Provide the connection of an empty archive."""
    with Archive.open(tmp_path / "a.sqlite3") as arch:
        yield arch.connection


@pytest.fixture
def conn(empty_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Provide an archive with two repos, three gates, one flaky tree."""
    insert(empty_conn, BASE + 100, "skip", saved=100.0)
    insert(empty_conn, BASE + 200, "skip", saved=50.0)
    insert(empty_conn, BASE + 300, "skip", saved=None)
    insert(empty_conn, BASE + 400, "fail", name="test", tree="t2", duration=5.0)
    insert(empty_conn, BASE + 500, "pass", name="test", tree="t2", duration=30.0)
    insert(empty_conn, BASE + DAY + 100, "uncached", repo=REPO_B, tree=None)
    return empty_conn


def test_summary_values(conn: sqlite3.Connection) -> None:
    """Summary aggregates the fixture events."""
    s = summary(conn, Filters())
    assert s["time_saved"] == 150.0
    assert s["skip_rate"] == pytest.approx(3 / 5)
    assert s["skips"] == 3
    assert s["runs"] == 6
    assert s["uncached"] == 1
    assert s["failures"] == 1
    assert s["unknown_saved_skips"] == 1
    assert s["flaky_gates"] == 1
    assert [d["day"] for d in s["daily"]] == ["2023-11-14", "2023-11-15"]
    assert s["daily"][0] == {"day": "2023-11-14", "saved": 150.0, "failures": 1, "runs": 5}
    json.dumps(s)


def test_empty_archive(empty_conn: sqlite3.Connection) -> None:
    """Every query handles an empty archive."""
    s = summary(empty_conn, Filters())
    assert s["runs"] == 0
    assert s["skip_rate"] is None
    assert s["daily"] == []
    assert gates(empty_conn, Filters()) == {"gates": []}
    assert flaky(empty_conn, Filters()) == {"gates": []}
    assert repos(empty_conn, Filters()) == {"repos": []}
    assert activity(empty_conn, Filters()) == {"events": [], "next_before": None}


def test_multi_repo_filter(conn: sqlite3.Connection) -> None:
    """Several repos match with IN; the unknown repo matches with IS NULL."""
    insert(conn, BASE + 600, "skip", repo=None, saved=7.0)
    assert summary(conn, Filters(repos=(REPO_A,)))["runs"] == 5
    assert summary(conn, Filters(repos=(REPO_A, REPO_B)))["runs"] == 6
    assert summary(conn, Filters(repos=(None,)))["runs"] == 1
    assert summary(conn, Filters(repos=(REPO_B, None)))["runs"] == 2
    assert summary(conn, Filters())["runs"] == 7


def test_repo_filter_and_range(conn: sqlite3.Connection) -> None:
    """Repo filters narrow rows, and the range is start-inclusive, end-exclusive."""
    assert summary(conn, Filters(repos=(REPO_B,)))["runs"] == 1
    assert summary(conn, Filters(repos=(REPO_A,)))["runs"] == 5
    assert summary(conn, Filters(start=BASE + 100, end=BASE + 300))["skips"] == 2
    s = summary(conn, Filters(start=BASE + 500))
    assert s["runs"] == 2
    assert s["flaky_gates"] == 0


def test_tz_moves_day_bucket(empty_conn: sqlite3.Connection) -> None:
    """An event at 23:30 UTC lands on the next day in Europe/Paris."""
    insert(empty_conn, BASE + 23.5 * 3600, "pass", duration=1.0)
    assert summary(empty_conn, Filters())["daily"][0]["day"] == "2023-11-14"
    assert summary(empty_conn, Filters(tz="Europe/Paris"))["daily"][0]["day"] == "2023-11-15"


def test_tz_dst_change(empty_conn: sqlite3.Connection) -> None:
    """Days bucket by local date across a DST change (Paris 2024-03-31, 01:00 UTC)."""
    midnight = 1_711_839_600.0  # 2024-03-31 00:00 local, +01:00
    # 2024-03-30 23:59 local, +01:00
    insert(empty_conn, midnight - 60, "pass", duration=1.0)
    # 2024-04-01 00:00 local, +02:00: the day is 23 hours long
    insert(empty_conn, midnight + 23 * 3600, "pass", duration=1.0)
    # 2024-03-31 23:50 local, +02:00
    insert(empty_conn, midnight + 22 * 3600 + 3000, "pass", duration=1.0)
    days = [d["day"] for d in summary(empty_conn, Filters(tz="Europe/Paris"))["daily"]]
    assert days == ["2024-03-30", "2024-03-31", "2024-04-01"]


@pytest.mark.parametrize(
    ("zone", "offset"), [("Asia/Kolkata", 5.5 * 3600), ("Asia/Kathmandu", 5.75 * 3600)]
)
def test_quarter_hour_offsets_split_days(
    empty_conn: sqlite3.Connection, zone: str, offset: float
) -> None:
    """Zones with half and quarter hour offsets split days at local midnight."""
    local_midnight = BASE + DAY - offset  # 2023-11-15 00:00 local
    insert(empty_conn, local_midnight - 60, "pass", duration=1.0)  # 2023-11-14 23:59 local
    insert(empty_conn, local_midnight, "pass", duration=1.0)  # 2023-11-15 00:00 local
    daily = summary(empty_conn, Filters(tz=zone))["daily"]
    assert [(d["day"], d["runs"]) for d in daily] == [("2023-11-14", 1), ("2023-11-15", 1)]


def test_negative_timestamp_buckets_by_floor(empty_conn: sqlite3.Connection) -> None:
    """An event just before the epoch lands on 1969-12-31 in UTC."""
    insert(empty_conn, -1.0, "pass", duration=1.0)
    insert(empty_conn, 0.0, "pass", duration=1.0)
    days = [d["day"] for d in summary(empty_conn, Filters())["daily"]]
    assert days == ["1969-12-31", "1970-01-01"]


def test_unknown_zone(empty_conn: sqlite3.Connection) -> None:
    """An unknown zone raises ValueError."""
    with pytest.raises(ValueError, match="time zone"):
        summary(empty_conn, Filters(tz="Mars/Base"))


def test_null_repo(empty_conn: sqlite3.Connection) -> None:
    """Events without a repo group under the unknown repo in every query."""
    insert(empty_conn, BASE, "fail", repo=None, tree="t9")
    insert(empty_conn, BASE + 1, "pass", repo=None, tree="t9", duration=1.0)
    assert summary(empty_conn, Filters())["flaky_gates"] == 1
    assert gates(empty_conn, Filters())["gates"][0]["repo_name"] == "unknown repo"
    assert gates(empty_conn, Filters())["gates"][0]["flaky"] is True
    f = flaky(empty_conn, Filters())["gates"]
    assert f[0]["repo"] is None
    assert len(f[0]["trees"][0]["runs"]) == 2


def test_flaky_pass_unrecorded_and_null_tree(empty_conn: sqlite3.Connection) -> None:
    """pass_unrecorded counts as a pass, and a null tree is never flaky."""
    insert(empty_conn, BASE, "fail", tree="a")
    insert(empty_conn, BASE + 1, "pass_unrecorded", tree="a")
    insert(empty_conn, BASE + 2, "fail", name="other", tree=None)
    insert(empty_conn, BASE + 3, "pass", name="other", tree=None, duration=1.0)
    assert [g["name"] for g in flaky(empty_conn, Filters())["gates"]] == ["lint"]
    assert summary(empty_conn, Filters())["flaky_gates"] == 1


def test_gates(conn: sqlite3.Connection) -> None:
    """Gates group by repo and name, ordered by time saved."""
    rows = gates(conn, Filters())["gates"]
    assert [(r["repo"], r["name"]) for r in rows] == [
        (REPO_A, "lint"),
        (REPO_B, "lint"),
        (REPO_A, "test"),
    ]
    lint, other, test = rows
    assert lint["repo_name"] == "proj"
    assert lint["time_saved"] == 150.0
    assert lint["skip_rate"] == 1.0
    assert lint["avg_run"] is None
    assert lint["flaky"] is False
    assert test["avg_run"] == 30.0
    assert test["median_run"] == 30.0
    assert test["failures"] == 1
    assert test["flaky"] is True
    assert test["last_run"] == BASE + 500
    assert other["skip_rate"] is None


def test_median_run(empty_conn: sqlite3.Connection) -> None:
    """Median and average cover pass events only."""
    for i, d in enumerate([10.0, 20.0, 60.0, 100.0]):
        insert(empty_conn, BASE + i, "pass", duration=d)
    insert(empty_conn, BASE + 9, "pass_unrecorded")
    row = gates(empty_conn, Filters())["gates"][0]
    assert row["avg_run"] == 47.5
    assert row["median_run"] == 40.0


def test_gate_detail_trend_and_flaky_trees(conn: sqlite3.Connection) -> None:
    """Gate detail returns the pass trend, recent rows, and flaky trees."""
    d = gate_detail(conn, Filters(), repo=REPO_A, name="test")
    assert d["repo_name"] == "proj"
    assert d["trend"] == [{"ts": BASE + 500, "duration": 30.0}]
    assert [r["outcome"] for r in d["recent"]] == ["pass", "fail"]
    assert d["flaky_trees"] == [{"tree": "t2", "fails": 1, "passes": 1, "last": BASE + 500}]
    assert gate_detail(conn, Filters(), repo=None, name="lint")["recent"] == []


def test_gate_detail_null_repo(empty_conn: sqlite3.Connection) -> None:
    """A None repo selects events recorded without a repo."""
    insert(empty_conn, BASE, "pass", repo=None, duration=2.0)
    d = gate_detail(empty_conn, Filters(), repo=None, name="lint")
    assert d["repo_name"] == "unknown repo"
    assert len(d["recent"]) == 1


def test_repos(conn: sqlite3.Connection) -> None:
    """Repos roll up their gates."""
    rows = repos(conn, Filters())["repos"]
    a = next(r for r in rows if r["repo"] == REPO_A)
    assert a["gates"] == 2
    assert a["runs"] == 5
    assert a["time_saved"] == 150.0
    assert a["failures"] == 1


def test_activity_paging(conn: sqlite3.Connection) -> None:
    """Pages continue from next_before and end with None."""
    first = activity(conn, Filters(), limit=4)
    assert len(first["events"]) == 4
    assert isinstance(first["next_before"], str)
    second = activity(conn, Filters(), limit=4, before=first["next_before"])
    assert len(second["events"]) == 2
    assert second["next_before"] is None
    assert second["events"][0]["repo_name"] == "proj"
    assert set(first["events"][0]) == {
        "ts",
        "repo",
        "repo_name",
        "name",
        "outcome",
        "duration",
        "saved",
        "exit_code",
        "reason",
        "tree",
        "reported",
    }


def test_activity_paging_identical_ts(empty_conn: sqlite3.Connection) -> None:
    """Events sharing one timestamp page without loss or duplication."""
    for i in range(7):
        insert(empty_conn, BASE, "pass", tree=f"t{i}", duration=1.0)
    seen: list[str] = []
    cursor = None
    while True:
        page = activity(empty_conn, Filters(), limit=3, before=cursor)
        seen += [e["tree"] for e in page["events"]]
        cursor = page["next_before"]
        if cursor is None:
            break
    assert sorted(seen) == [f"t{i}" for i in range(7)]


@pytest.mark.parametrize(
    "cursor",
    [
        "nope",
        "abc:1",
        "1.0:x",
        "nan:1",
        "inf:1",
        ":",
        "1.0:99999999999999999999",
        "1_0:1",
        " 1.0:1",
        "1.0: 1",
        "1.0:1_0",
        "1.0:+1",
    ],
)
def test_activity_bad_cursor(conn: sqlite3.Connection, cursor: str) -> None:
    """A malformed cursor raises ValueError."""
    with pytest.raises(ValueError, match="cursor"):
        activity(conn, Filters(), before=cursor)


def test_activity_exponent_cursor_accepted(conn: sqlite3.Connection) -> None:
    """A cursor in the exponent form repr gives very large floats is valid."""
    assert len(activity(conn, Filters(), before="1e+20:1")["events"]) == 6


def test_activity_limit_clamped(conn: sqlite3.Connection) -> None:
    """Limits clamp to 1..500."""
    assert len(activity(conn, Filters(), limit=0)["events"]) == 1
    assert len(activity(conn, Filters(), limit=10000)["events"]) == 6


def test_activity_limit_capped_at_500(empty_conn: sqlite3.Connection) -> None:
    """A page never holds more than 500 events, however large the limit."""
    empty_conn.executemany(
        "INSERT INTO events (line_hash, ts, name, paths, outcome) VALUES (?, ?, 'lint', '[]', 'pass')",
        [(f"h{i}", BASE + i) for i in range(501)],
    )
    empty_conn.commit()
    page = activity(empty_conn, Filters(), limit=10_000)
    assert len(page["events"]) == 500
    assert page["next_before"] is not None


def test_activity_outcome_filter(conn: sqlite3.Connection) -> None:
    """An outcome filter keeps only events with that outcome, within the other filters."""
    fails = activity(conn, Filters(repos=(REPO_A,)), outcome="fail")["events"]
    assert [(e["name"], e["outcome"]) for e in fails] == [("test", "fail")]
    skips = activity(conn, Filters(), outcome="skip", limit=2)
    assert [e["outcome"] for e in skips["events"]] == ["skip", "skip"]
    rest = activity(conn, Filters(), outcome="skip", before=skips["next_before"])
    assert [e["outcome"] for e in rest["events"]] == ["skip"]
    assert rest["next_before"] is None
    assert activity(conn, Filters(repos=(REPO_B,)), outcome="fail")["events"] == []


def test_activity_unknown_outcome(conn: sqlite3.Connection) -> None:
    """An unknown outcome raises ValueError."""
    with pytest.raises(ValueError, match="outcome"):
        activity(conn, Filters(), outcome="exploded")


def test_flaky(conn: sqlite3.Connection) -> None:
    """Flaky lists trees with a fail and a pass."""
    g = flaky(conn, Filters())["gates"]
    assert len(g) == 1
    assert g[0]["name"] == "test"
    assert g[0]["tree_count"] == 1
    assert g[0]["last_seen"] == BASE + 500
    assert [r["outcome"] for r in g[0]["trees"][0]["runs"]] == ["fail", "pass"]


def test_repo_names_use_the_work_tree_folder() -> None:
    """Repo names come from the work tree directory when possible."""
    assert repo_names(["/x/proj/.git", "/x/bare.git", None]) == {
        "/x/proj/.git": "proj",
        "/x/bare.git": "bare.git",
        None: "unknown repo",
    }


def test_repo_names_add_parents_until_unique() -> None:
    """Repos that share a folder name get as many parent folders as it takes to tell them apart."""
    names = repo_names(
        [
            "/home/a/code/app/.git",
            "/home/b/work/app/.git",
            "/x/one/repo/.git",
            "/y/one/repo/.git",
            "/x/proj/.git",
            None,
        ]
    )
    assert names == {
        "/home/a/code/app/.git": "app (code)",
        "/home/b/work/app/.git": "app (work)",
        "/x/one/repo/.git": "repo (x/one)",
        "/y/one/repo/.git": "repo (y/one)",
        "/x/proj/.git": "proj",
        None: "unknown repo",
    }


def test_repo_names_fall_back_to_the_full_path() -> None:
    """Repos that differ only in their own folder form keep their full path."""
    assert repo_names(["/x/app/.git", "/x/app"]) == {
        "/x/app/.git": "/x/app/.git",
        "/x/app": "/x/app",
    }


def test_repo_names_show_the_root_for_a_repo_at_the_root() -> None:
    """A repo directly under the filesystem root gets the root as its parent label."""
    assert repo_names(["/app/.git", "/x/app/.git"]) == {
        "/app/.git": "app (/)",
        "/x/app/.git": "app (x)",
    }


def test_activity_names_a_repo_added_after_the_name_lookup(
    empty_conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An event from a repo that ingest adds mid-query still gets its folder name."""
    insert(empty_conn, BASE, "pass", repo="/a/new/.git", duration=1.0)
    monkeypatch.setattr(queries, "_DISTINCT_REPOS", "SELECT NULL WHERE 0")
    assert [e["repo_name"] for e in activity(empty_conn, Filters())["events"]] == ["new"]


def test_repeated_repo_names_are_distinct_in_every_view(empty_conn: sqlite3.Connection) -> None:
    """Every view names a repo the same way, even when a filter leaves out the repo it clashes with."""
    insert(empty_conn, BASE, "pass", repo="/a/app/.git", duration=1.0)
    insert(empty_conn, BASE + 1, "pass", repo="/b/app/.git", duration=1.0)
    assert sorted(r["repo_name"] for r in repos(empty_conn, Filters())["repos"]) == [
        "app (a)",
        "app (b)",
    ]
    only_a = Filters(repos=("/a/app/.git",))
    assert [g["repo_name"] for g in gates(empty_conn, only_a)["gates"]] == ["app (a)"]
    assert [e["repo_name"] for e in activity(empty_conn, only_a)["events"]] == ["app (a)"]
    detail = gate_detail(empty_conn, Filters(), repo="/b/app/.git", name="lint")
    assert detail["repo_name"] == "app (b)"
    assert [e["repo_name"] for e in detail["recent"]] == ["app (b)"]


def test_gate_detail_ignores_filter_repo(conn: sqlite3.Connection) -> None:
    """Gate detail selects by its own repo argument, not by the filter repo."""
    body = gate_detail(conn, Filters(repos=(REPO_B,)), repo=REPO_A, name="lint")
    assert body["repo"] == REPO_A
    assert len(body["recent"]) == 3
    assert {r["repo"] for r in body["recent"]} == {REPO_A}


def test_flaky_orders_trees_newest_first(empty_conn: sqlite3.Connection) -> None:
    """Each gate lists its flaky trees by last run, and counts them."""
    insert(empty_conn, BASE + 10, "fail", tree="old")
    insert(empty_conn, BASE + 20, "pass", tree="old", duration=1.0)
    insert(empty_conn, BASE + 30, "fail", tree="new")
    insert(empty_conn, BASE + 40, "pass", tree="new", duration=1.0)
    insert(empty_conn, BASE + 50, "pass", tree="clean", duration=1.0)
    (gate,) = flaky(empty_conn, Filters())["gates"]
    assert gate["tree_count"] == 2
    assert gate["last_seen"] == BASE + 40
    assert [t["tree"] for t in gate["trees"]] == ["new", "old"]
    assert [r["outcome"] for r in gate["trees"][0]["runs"]] == ["fail", "pass"]


def test_unknown_outcomes_are_not_counted(conn: sqlite3.Connection) -> None:
    """Rows with an outcome from a newer gate-cache are stored but left out of every result."""
    filters = Filters()

    def snapshot() -> list[object]:
        return [
            summary(conn, filters),
            gates(conn, filters),
            repos(conn, filters),
            flaky(conn, filters),
            activity(conn, filters),
            gate_detail(conn, filters, repo=REPO_A, name="lint"),
            gate_detail(conn, filters, repo=REPO_A, name="test"),
        ]

    before = snapshot()
    insert(conn, BASE + 150, "novel", saved=10.0, duration=1.0)
    insert(conn, BASE + 450, "novel", name="test", tree="t2", duration=2.0)
    insert(conn, BASE + 600, "novel", repo="/x/new/.git", name="ghost", tree="t9")
    assert conn.execute("SELECT COUNT(*) FROM events WHERE outcome = 'novel'").fetchone()[0] == 3
    assert snapshot() == before
    ghost = gate_detail(conn, filters, repo="/x/new/.git", name="ghost")
    assert ghost["recent"] == []
    assert ghost["trend"] == []


def test_hourly_has_168_cells(empty_conn: sqlite3.Connection) -> None:
    """An empty archive still yields every hour of the week."""
    cells = hourly(empty_conn, Filters())["cells"]
    assert len(cells) == 168
    assert [(c["weekday"], c["hour"]) for c in cells] == [
        (d, h) for d in range(7) for h in range(24)
    ]
    assert all(c["runs"] == 0 and c["saved"] == 0.0 and c["failures"] == 0 for c in cells)


def test_hourly_buckets_in_zone(empty_conn: sqlite3.Connection) -> None:
    """Events land in the local weekday and hour of the filter's zone."""
    insert(empty_conn, BASE + 3600, "skip", saved=5.0)
    cells = hourly(empty_conn, Filters(tz="America/New_York"))["cells"]
    hit = [c for c in cells if c["runs"]]
    assert hit == [{"weekday": 1, "hour": 20, "runs": 1, "saved": 5.0, "failures": 0}]


def test_hourly_sunday_failures_and_accumulation(empty_conn: sqlite3.Connection) -> None:
    """Sunday is weekday 0, and events in one hour sum into a single cell."""
    sunday = BASE - 2 * DAY + 10 * 3600
    insert(empty_conn, sunday + 60, "skip", saved=10.0)
    insert(empty_conn, sunday + 1200, "fail", tree="t2", duration=4.0)
    insert(empty_conn, sunday + 2400, "pass", tree="t3", duration=7.0)
    cells = hourly(empty_conn, Filters(tz="UTC"))["cells"]
    hit = [c for c in cells if c["runs"]]
    assert hit == [{"weekday": 0, "hour": 10, "runs": 3, "saved": 10.0, "failures": 1}]


def test_summary_outcomes(conn: sqlite3.Connection) -> None:
    """Summary counts every outcome separately."""
    assert summary(conn, Filters())["outcomes"] == {
        "skip": 3,
        "pass": 1,
        "pass_unrecorded": 0,
        "fail": 1,
        "uncached": 1,
    }


def test_previous_window_totals(empty_conn: sqlite3.Connection) -> None:
    """Previous totals cover the window of equal length before the start."""
    insert(empty_conn, BASE, "skip", saved=10.0)
    insert(empty_conn, BASE + DAY + 100, "skip", saved=30.0)
    s = summary(empty_conn, Filters(start=BASE + DAY, end=BASE + 2 * DAY), now=BASE + 2 * DAY)
    assert s["previous"]["time_saved"] == 10.0
    assert s["previous"]["days"] == 1.0


def test_previous_none_for_all_time(conn: sqlite3.Connection) -> None:
    """An unbounded range has no previous window."""
    assert summary(conn, Filters(), now=BASE + 3 * DAY)["previous"] is None


def test_previous_none_before_first_event(empty_conn: sqlite3.Connection) -> None:
    """No previous window starts before the archive's first event."""
    insert(empty_conn, BASE + DAY + 100, "skip", saved=30.0)
    s = summary(empty_conn, Filters(start=BASE + DAY, end=BASE + 2 * DAY), now=BASE + 2 * DAY)
    assert s["previous"] is None


def test_previous_none_beyond_retention(empty_conn: sqlite3.Connection) -> None:
    """No previous window reaches past the retention period."""
    insert(empty_conn, BASE, "skip", saved=1.0)
    now = BASE + 400 * DAY
    assert summary(empty_conn, Filters(start=now - 365 * DAY), now=now)["previous"] is None


def test_previous_window_ignores_repo_filter_for_earliest(
    empty_conn: sqlite3.Connection,
) -> None:
    """The earliest-event check spans every repo."""
    insert(empty_conn, BASE, "skip", repo=REPO_B, saved=1.0)
    insert(empty_conn, BASE + DAY + 100, "skip", saved=2.0)
    current = Filters(repos=(REPO_A,), start=BASE + DAY, end=BASE + 2 * DAY)
    prev = previous_window(empty_conn, current, now=BASE + 2 * DAY)
    assert prev == Filters(repos=(REPO_A,), start=BASE, end=BASE + DAY)


def test_previous_window_open_end_uses_now(empty_conn: sqlite3.Connection) -> None:
    """An open-ended range compares against a window of the same length ending at its start."""
    insert(empty_conn, BASE, "skip", saved=1.0)
    prev = previous_window(empty_conn, Filters(start=BASE + DAY), now=BASE + 2 * DAY)
    assert prev is not None
    assert (prev.start, prev.end) == (BASE, BASE + DAY)


def test_previous_flaky_gates(empty_conn: sqlite3.Connection) -> None:
    """Previous flaky gates use the same definition as the current window."""
    insert(empty_conn, BASE, "skip", name="other", saved=1.0)
    insert(empty_conn, BASE + 10, "fail", tree="t9")
    insert(empty_conn, BASE + 20, "pass", tree="t9")
    s = summary(empty_conn, Filters(start=BASE + DAY, end=BASE + 2 * DAY), now=BASE + 2 * DAY)
    assert s["previous"]["flaky_gates"] == 1
    assert s["previous"]["failures"] == 1


def test_reasons_counts_and_order(empty_conn: sqlite3.Connection) -> None:
    """Reasons count uncached and unrecorded passes only, most common first."""
    off = "GATE_CACHE_DISABLE is set"
    changed = "files changed during the run"
    insert(empty_conn, BASE + 1, "uncached", tree="t1", reason=off)
    insert(empty_conn, BASE + 2, "uncached", tree="t2", reason=off)
    insert(empty_conn, BASE + 3, "pass_unrecorded", tree="t3", reason=changed)
    insert(empty_conn, BASE + 4, "fail", tree="t4", reason="ignored")
    insert(empty_conn, BASE + 5, "uncached", tree="t5")
    assert reasons(empty_conn, Filters())["reasons"] == [
        {"outcome": "uncached", "reason": off, "count": 2},
        {"outcome": "pass_unrecorded", "reason": changed, "count": 1},
    ]


def test_reasons_same_reason_under_two_outcomes(empty_conn: sqlite3.Connection) -> None:
    """One reason recorded under two outcomes gives one row per outcome."""
    reason = "files changed during the run"
    insert(empty_conn, BASE + 1, "uncached", tree="t1", reason=reason)
    insert(empty_conn, BASE + 2, "pass_unrecorded", tree="t2", reason=reason)
    insert(empty_conn, BASE + 3, "pass_unrecorded", tree="t3", reason=reason)
    assert reasons(empty_conn, Filters())["reasons"] == [
        {"outcome": "pass_unrecorded", "reason": reason, "count": 2},
        {"outcome": "uncached", "reason": reason, "count": 1},
    ]


def test_activity_reason_filter(empty_conn: sqlite3.Connection) -> None:
    """The reason filter keeps only events with that exact reason."""
    insert(empty_conn, BASE + 1, "uncached", tree="t1", reason="a")
    insert(empty_conn, BASE + 2, "uncached", tree="t2", reason="b")
    insert(empty_conn, BASE + 3, "pass", tree="t3")
    events = activity(empty_conn, Filters(), reason="a")["events"]
    assert [e["tree"] for e in events] == ["t1"]


def _passes(
    conn: sqlite3.Connection, start: float, name: str, duration: float, count: int = 5
) -> None:
    """Insert count passing runs of a gate from start, one second apart."""
    for i in range(count):
        insert(conn, start + i, "pass", name=name, duration=duration, tree=f"{name}{start}{i}")


def _two_windows(conn: sqlite3.Connection, name: str, before: float, now: float) -> None:
    """Insert five passes in the previous window and five in the current one."""
    _passes(conn, BASE, name, before)
    _passes(conn, BASE + DAY + 10, name, now)


CURRENT = Filters(start=BASE + DAY)


def test_slowdowns_ranks_by_relative_change(empty_conn: sqlite3.Connection) -> None:
    """Gates sort by relative growth, not absolute seconds."""
    _two_windows(empty_conn, "b", 100.0, 120.0)
    _two_windows(empty_conn, "a", 10.0, 15.0)
    result = slowdowns(empty_conn, CURRENT, now=BASE + 2 * DAY)
    assert result["comparable"] is True
    assert [g["name"] for g in result["gates"]] == ["a", "b"]
    first = result["gates"][0]
    assert first == {
        "repo": REPO_A,
        "repo_name": "proj",
        "name": "a",
        "before": 10.0,
        "now": 15.0,
        "change": 0.5,
    }


def test_slowdowns_needs_five_runs_each_side(empty_conn: sqlite3.Connection) -> None:
    """A gate with fewer than five passes in either window is excluded."""
    _passes(empty_conn, BASE, "lint", 10.0, count=4)
    _passes(empty_conn, BASE + DAY + 10, "lint", 20.0)
    assert slowdowns(empty_conn, CURRENT, now=BASE + 2 * DAY)["gates"] == []


def test_slowdowns_ignores_speedups(empty_conn: sqlite3.Connection) -> None:
    """Faster or unchanged gates are not slowdowns."""
    _two_windows(empty_conn, "fast", 20.0, 10.0)
    _two_windows(empty_conn, "same", 10.0, 10.0)
    result = slowdowns(empty_conn, CURRENT, now=BASE + 2 * DAY)
    assert result == {"gates": [], "comparable": True}


def test_slowdowns_not_comparable_for_all_time(conn: sqlite3.Connection) -> None:
    """An unbounded range has no previous window."""
    assert slowdowns(conn, Filters(), now=BASE + 3 * DAY) == {"gates": [], "comparable": False}


def test_slowdowns_limit(empty_conn: sqlite3.Connection) -> None:
    """Only the top gates are returned."""
    for i in range(3):
        _two_windows(empty_conn, f"g{i}", 10.0, 11.0 + i)
    result = slowdowns(empty_conn, CURRENT, now=BASE + 2 * DAY, limit=2)
    assert [g["name"] for g in result["gates"]] == ["g2", "g1"]


def test_slowdowns_skips_zero_previous_median(empty_conn: sqlite3.Connection) -> None:
    """A zero previous median has no relative change and is not listed."""
    _two_windows(empty_conn, "lint", 0.0, 2.0)
    result = slowdowns(empty_conn, CURRENT, now=BASE + 2 * DAY)
    assert result == {"gates": [], "comparable": True}


def test_slowdowns_skips_gate_new_in_current_window(empty_conn: sqlite3.Connection) -> None:
    """A gate with no previous passes is not listed."""
    _passes(empty_conn, BASE, "old", 10.0)
    _passes(empty_conn, BASE + DAY + 10, "new", 10.0)
    assert slowdowns(empty_conn, CURRENT, now=BASE + 2 * DAY)["gates"] == []


@pytest.mark.parametrize("reported", [True, False])
def test_activity_reports_reported_flag(empty_conn: sqlite3.Connection, *, reported: bool) -> None:
    """An event row says whether the run reported another run's failure."""
    insert(empty_conn, BASE, "fail", reported=reported)
    assert activity(empty_conn, Filters())["events"][0]["reported"] is reported


def test_gate_detail_names_a_repo_the_archive_lacks(conn: sqlite3.Connection) -> None:
    """A detail request for a repo with no events still gets the repo's folder name."""
    assert gate_detail(conn, Filters(), repo="/z/gone/.git", name="lint")["repo_name"] == "gone"


def test_repo_names_avoid_another_repos_folder_name() -> None:
    """A label with parent folders never repeats a folder name that another repo already shows."""
    names = repo_names(["/a/code/app/.git", "/b/work/app/.git", "/c/app (code)/.git"])
    assert names == {
        "/a/code/app/.git": "app (a/code)",
        "/b/work/app/.git": "app (b/work)",
        "/c/app (code)/.git": "app (code)",
    }


def test_summary_net_saved(empty_conn: sqlite3.Connection) -> None:
    """Net time saved subtracts overhead and waits, and counts runs missing either."""
    insert(empty_conn, BASE + 1, "skip", saved=100.0, overhead=1.0, waited=20.0, wait_known=True)
    insert(empty_conn, BASE + 2, "pass", duration=5.0, overhead=2.0, wait_known=True)
    insert(empty_conn, BASE + 3, "pass", duration=5.0, overhead=3.0)
    insert(empty_conn, BASE + 4, "skip", saved=10.0)
    insert(empty_conn, BASE + 5, "uncached", tree=None)
    s = summary(empty_conn, Filters())
    assert (s["overhead"], s["waited"]) == (6.0, 20.0)
    assert s["net_saved"] == pytest.approx(110.0 - 6.0 - 20.0)
    # The uncached run never checks the cache, so it is not missing a cost.
    assert s["cost_unknown_runs"] == 2


def test_summary_net_saved_can_be_negative(empty_conn: sqlite3.Connection) -> None:
    """Overhead with no skips gives a negative net, and the previous window carries it."""
    insert(empty_conn, BASE + DAY + 1, "pass", duration=5.0, overhead=2.0, wait_known=True)
    insert(empty_conn, BASE, "skip", saved=4.0, overhead=1.0, wait_known=True)
    s = summary(empty_conn, Filters(start=BASE + DAY, end=BASE + 2 * DAY), now=BASE + 2 * DAY)
    assert s["net_saved"] == -2.0
    assert s["previous"]["net_saved"] == 3.0
    assert "cost_unknown_runs" not in s["previous"]


def test_summary_previous_net_saved_needs_known_costs(empty_conn: sqlite3.Connection) -> None:
    """The previous net saved is None when either window holds a run with no recorded cost."""
    insert(empty_conn, BASE + DAY + 1, "pass", duration=5.0, overhead=2.0, wait_known=True)
    insert(empty_conn, BASE, "skip", saved=4.0)
    s = summary(empty_conn, Filters(start=BASE + DAY, end=BASE + 2 * DAY), now=BASE + 2 * DAY)
    assert s["cost_unknown_runs"] == 0
    assert s["previous"]["net_saved"] is None


def test_coalescing(empty_conn: sqlite3.Connection) -> None:
    """Runs that waited split into skipped, reported, and ran, with wait totals."""
    insert(empty_conn, BASE + 1, "skip", saved=60.0, waited=10.0, wait_known=True)
    insert(empty_conn, BASE + 2, "skip", saved=30.0, waited=2.0, wait_known=True)
    insert(
        empty_conn,
        BASE + 3,
        "fail",
        waited=4.0,
        wait_known=True,
        reason="failed in another run, not rerun",
        reported=True,
    )
    insert(
        empty_conn,
        BASE + 4,
        "pass",
        duration=9.0,
        waited=900.0,
        wait_known=True,
        wait_timed_out=True,
    )
    insert(empty_conn, BASE + 5, "pass", duration=9.0, wait_known=True)
    insert(empty_conn, BASE + 6, "pass", duration=9.0)
    insert(empty_conn, BASE + 7, "uncached", tree=None)
    insert(empty_conn, BASE + 8, "uncached", tree=None, waited=6.0, wait_known=True)
    c = coalescing(empty_conn, Filters())
    assert c == {
        "runs": 7,
        "unknown_runs": 1,
        "waited": 5,
        "skipped": 2,
        "reported": 1,
        "ran": 2,
        "timed_out": 1,
        "total_wait": 922.0,
        "median_wait": 6.0,
        "saved": 90.0,
    }
    json.dumps(c)


def test_coalescing_empty(empty_conn: sqlite3.Connection) -> None:
    """No waits gives zero counts and no median."""
    c = coalescing(empty_conn, Filters())
    assert (c["waited"], c["ran"], c["median_wait"], c["total_wait"]) == (0, 0, None, 0.0)


def insert_raw(
    conn: sqlite3.Connection,
    ts: float,
    outcome: str = "pass",
    *,
    repo: str | None = REPO_A,
    name: str = "lint",
    saved: float | None = None,
    raw: dict[str, object] | str | None = None,
) -> None:
    """Insert one event whose raw line holds the given fields."""
    conn.execute(
        "INSERT INTO events (line_hash, ts, repo, name, paths, outcome, saved, raw)"
        " VALUES (?, ?, ?, ?, '[]', ?, ?, ?)",
        (
            f"r{conn.total_changes}-{ts}",
            ts,
            repo,
            name,
            outcome,
            saved,
            json.dumps(raw) if isinstance(raw, dict) else raw,
        ),
    )
    conn.commit()


def _labels(conn: sqlite3.Connection, by: str, filters: Filters | None = None) -> list[str]:
    return [r["label"] for r in queries.breakdown(conn, filters or Filters(), by=by)["rows"]]


def test_breakdown_repo_keys_rows_by_repo(conn: sqlite3.Connection) -> None:
    """Repo rows carry the repo, its display name, and a key that holds only the repo."""
    rows = queries.breakdown(conn, Filters(), by="repo")["rows"]
    assert [(r["repo"], r["label"], json.loads(r["key"])) for r in rows] == [
        (REPO_A, "proj", [REPO_A]),
        (REPO_B, "other", [REPO_B]),
    ]


def test_trigger_labels_cover_every_trigger() -> None:
    """Every trigger the recorder writes has a display name."""
    assert set(queries.TRIGGER_LABELS) == set(get_args(Trigger))


def test_breakdown_gate_names_repo_only_when_rows_mix_repos(
    empty_conn: sqlite3.Connection,
) -> None:
    """Gate labels add the repo name only when the rows come from more than one repo."""
    insert_raw(empty_conn, BASE + 1, "skip", saved=10.0)
    insert_raw(empty_conn, BASE + 2, repo=REPO_B)
    assert _labels(empty_conn, "gate") == ["lint · proj", "lint · other"]
    assert _labels(empty_conn, "gate", Filters(repos=(REPO_A,))) == ["lint"]
    row = queries.breakdown(empty_conn, Filters(), by="gate")["rows"][0]
    assert (row["repo"], row["name"], row["title"]) == (REPO_A, "lint", REPO_A)


def test_breakdown_source_names_agents_and_buckets_missing(
    empty_conn: sqlite3.Connection,
) -> None:
    """Sources split agent runs by agent and group runs with no trigger under a labeled row."""
    insert_raw(empty_conn, BASE + 1, "skip", saved=30.0, raw={"trigger": "agent", "agent": "codex"})
    insert_raw(empty_conn, BASE + 2, "skip", saved=20.0, raw={"trigger": "hook"})
    insert_raw(empty_conn, BASE + 3, "skip", saved=10.0, raw={"trigger": "agent"})
    insert_raw(empty_conn, BASE + 7, raw={"trigger": "agent", "agent": ""})
    insert_raw(empty_conn, BASE + 4, raw={"trigger": "nightly"})
    insert_raw(empty_conn, BASE + 5, raw=None)
    insert_raw(empty_conn, BASE + 6, raw="not json")
    rows = queries.breakdown(empty_conn, Filters(), by="source")["rows"]
    assert [(r["label"], r["runs"], r["missing"]) for r in rows] == [
        ("Agent: codex", 1, False),
        ("Git hook", 1, False),
        ("Agent", 2, False),
        ("No source recorded", 2, True),
        ("nightly", 1, False),
    ]


def test_breakdown_branch_groups_per_repo_and_buckets_missing(
    empty_conn: sqlite3.Connection,
) -> None:
    """Branches group within each repo, and runs without a branch form their own row."""
    insert_raw(empty_conn, BASE + 1, "skip", saved=5.0, raw={"branch": "main"})
    insert_raw(empty_conn, BASE + 2, raw={"branch": "main"})
    insert_raw(empty_conn, BASE + 3, raw={"branch": None})
    insert_raw(empty_conn, BASE + 4, repo=REPO_B, raw={"branch": "main"})
    rows = queries.breakdown(empty_conn, Filters(repos=(REPO_A,)), by="branch")["rows"]
    assert [(r["label"], r["runs"], r["missing"]) for r in rows] == [
        ("main", 2, False),
        ("No branch recorded", 1, True),
    ]
    assert sorted(_labels(empty_conn, "branch")) == [
        "No branch recorded · proj",
        "main · other",
        "main · proj",
    ]


def test_breakdown_machine_labels_by_latest_host(empty_conn: sqlite3.Connection) -> None:
    """Machines show their newest host, with an ID prefix when two machines share a host."""
    m1, m2, m3 = "a" * 32, "b" * 32, "c" * 32
    insert_raw(empty_conn, BASE + 1, raw={"machine": m1, "host": "old"})
    insert_raw(empty_conn, BASE + 2, raw={"machine": m1, "host": "laptop"})
    insert_raw(empty_conn, BASE + 3, raw={"machine": m2, "host": "laptop"})
    insert_raw(empty_conn, BASE + 4, raw={"machine": m3, "host": "desk"})
    insert_raw(empty_conn, BASE + 5, raw={"machine": m3})
    insert_raw(empty_conn, BASE + 6, raw={})
    rows = queries.breakdown(empty_conn, Filters(), by="machine")["rows"]
    assert sorted((r["label"], r["runs"], r["missing"]) for r in rows) == [
        ("Machine cccccccc", 2, False),
        ("No machine recorded", 1, True),
        ("laptop (aaaaaaaa)", 2, False),
        ("laptop (bbbbbbbb)", 1, False),
    ]
    missing = next(r for r in rows if r["missing"])
    assert "older gate-cache versions" in missing["title"]


def test_breakdown_rejects_unknown_dimension(conn: sqlite3.Connection) -> None:
    """An unknown dimension is a ValueError naming the choices."""
    with pytest.raises(ValueError, match="expected one of repo, gate"):
        queries.breakdown(conn, Filters(), by="tool")


def test_activity_group_lists_one_breakdown_row(empty_conn: sqlite3.Connection) -> None:
    """A breakdown row's key filters activity to exactly that row's runs."""
    insert_raw(empty_conn, BASE + 1, raw={"branch": "main"})
    insert_raw(empty_conn, BASE + 2, raw={"branch": "dev"})
    insert_raw(empty_conn, BASE + 3, raw={"branch": None})
    insert_raw(empty_conn, BASE + 4, repo=REPO_B, raw={"branch": "main"})
    for row in queries.breakdown(empty_conn, Filters(), by="branch")["rows"]:
        events = activity(empty_conn, Filters(), group=("branch", row["key"]))["events"]
        assert len(events) == row["runs"]
        assert {e["repo"] for e in events} == {row["repo"]}


@pytest.mark.parametrize(
    "key", ["nope", "[]", '["a"]', '[1, "main"]', '{"a": 1}', '["/x/.git", "main", null]']
)
def test_group_filter_rejects_keys_that_do_not_fit(key: str) -> None:
    """A key that is not a JSON list of one text or null per group column is a ValueError."""
    with pytest.raises(ValueError, match="malformed branch key"):
        queries.group_filter("branch", key)
