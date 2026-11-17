"""Tests for the dashboard metric queries."""

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from gate_cache.stats.archive import Archive
from gate_cache.stats.queries import (
    Filters,
    activity,
    flaky,
    gate_detail,
    gates,
    repo_name,
    repos,
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
) -> None:
    """Insert one event row."""
    conn.execute(
        "INSERT INTO events (line_hash, ts, repo, name, tree, paths, outcome, duration, saved)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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


def test_repo_filter_and_range(conn: sqlite3.Connection) -> None:
    """Repo filters narrow rows, and the range is start-inclusive, end-exclusive."""
    assert summary(conn, Filters(repo=REPO_B))["runs"] == 1
    assert summary(conn, Filters(repo=REPO_A))["runs"] == 5
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
    fails = activity(conn, Filters(repo=REPO_A), outcome="fail")["events"]
    assert [(e["name"], e["outcome"]) for e in fails] == [("test", "fail")]
    skips = activity(conn, Filters(), outcome="skip", limit=2)
    assert [e["outcome"] for e in skips["events"]] == ["skip", "skip"]
    rest = activity(conn, Filters(), outcome="skip", before=skips["next_before"])
    assert [e["outcome"] for e in rest["events"]] == ["skip"]
    assert rest["next_before"] is None
    assert activity(conn, Filters(repo=REPO_B), outcome="fail")["events"] == []


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


def test_repo_name() -> None:
    """Repo names come from the work tree directory when possible."""
    assert repo_name("/x/proj/.git") == "proj"
    assert repo_name("/x/bare.git") == "bare.git"
    assert repo_name(None) == "unknown repo"


def test_gate_detail_ignores_filter_repo(conn: sqlite3.Connection) -> None:
    """Gate detail selects by its own repo argument, not by the filter repo."""
    body = gate_detail(conn, Filters(repo=REPO_B), repo=REPO_A, name="lint")
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
