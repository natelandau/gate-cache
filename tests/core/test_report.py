"""Tests for the stats report builder and its access to the record."""

import json
import os
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from gate_cache.git import git_common_dir
from gate_cache.stats.archive import ARCHIVE_NAME, Archive
from gate_cache.stats.lock import InstanceLock, running_url
from gate_cache.stats.queries import FAILED_TESTS_SHOWN, REPORT_PROBLEM_RUNS
from gate_cache.stats.recorder import INBOX_NAME
from gate_cache.stats.report import (
    REPORT_SCHEMA,
    AmbiguousRepoError,
    RepoNotFoundError,
    Window,
    gate_report,
    open_record,
    resolve_repo,
    suite_report,
)
from gate_cache.stats.report_text import KEYED_STATUS, UNKNOWN_STATUS, render_gate
from tests.conftest import BASE, DAY, REPO_A, REPO_B, insert, insert_results

WINDOW = Window(start=BASE, end=BASE + 2 * DAY, tz=ZoneInfo("UTC"))
GATE_KEYS = {
    "name",
    "command",
    "paths",
    "runs",
    "skip_rate",
    "failures",
    "median_run",
    "p90_run",
    "time_spent",
    "time_saved",
    "fail_time",
    "last_run",
    "flaky",
    "slowdown",
    "uncached",
    "waits",
    "tests",
    "spot_checks",
}


def _seed_two_gates(conn: sqlite3.Connection) -> None:
    """Record a clean `lint` and a flaky, costly `test` that waited and ran uncached."""
    insert(conn, BASE + 100, "skip", saved=100.0, overhead=0.5)
    insert(conn, BASE + 200, "pass", duration=2.0, overhead=0.25)
    insert(conn, BASE + 300, "fail", name="test", tree="t2", duration=5.0, exit_code=1)
    insert(conn, BASE + 400, "pass", name="test", tree="t2", duration=30.0, waited=3.0)
    insert(
        conn, BASE + 500, "pass_unrecorded", name="test", tree="t3", duration=20.0,
        reason="files changed",
    )  # fmt: skip


def test_suite_report_shape(empty_conn: sqlite3.Connection) -> None:
    """The suite view lists every gate by time spent with nulls where a note does not apply."""
    _seed_two_gates(empty_conn)

    report = suite_report(empty_conn, repos=(REPO_A,), window=WINDOW, recording=True)

    assert set(report) == {"schema", "repo", "repo_name", "window", "totals", "gates"}
    assert report["schema"] == REPORT_SCHEMA
    assert (report["repo"], report["repo_name"]) == (REPO_A, "proj")
    assert report["window"] == {
        "since": "2023-11-14T00:00:00Z",
        "until": "2023-11-16T00:00:00Z",
        "days": 2.0,
    }
    assert report["totals"] == {
        "runs": 5,
        "skips": 1,
        "time_saved": 100.0,
        "time_spent": 57.0,
        "fail_time": 5.0,
        "overhead": 0.75,
        "spot_checks": 0,
        "spot_check_failures": 0,
    }
    test, lint = report["gates"]
    assert [test["name"], lint["name"]] == ["test", "lint"]
    assert set(test) == set(lint) == GATE_KEYS
    assert (test["command"], test["paths"]) == ("test", ["src"])
    assert test["flaky"] == {
        "trees": 1,
        "fails": 1,
        "passes": 1,
        "last_seen": "2023-11-14T00:06:40Z",
    }
    assert test["uncached"] == [
        {"outcome": "pass_unrecorded", "reason": "files changed", "count": 1}
    ]
    assert test["waits"]["waited"] == 1
    assert lint["last_run"] == "2023-11-14T00:03:20Z"
    assert lint["uncached"] == []
    for key in ("flaky", "slowdown", "waits", "spot_checks"):
        assert lint[key] is None, key


def test_suite_report_shows_every_slowdown(empty_conn: sqlite3.Connection) -> None:
    """Every gate that slowed down carries its slowdown, not only the dashboard's top five."""
    # Slowdowns compare against the window before, which must fall inside retention.
    start = float(int(time.time()) - 10 * int(DAY))
    names = [f"g{i}" for i in range(7)]
    for i, name in enumerate(names):
        for run in range(5):
            insert(empty_conn, start + run, "pass", name=name, tree=f"a{run}", duration=10.0)
            insert(
                empty_conn, start + DAY + 10 + run, "pass", name=name, tree=f"b{run}",
                duration=11.0 + i,
            )  # fmt: skip
    window = Window(start=start + DAY, end=start + 2 * DAY, tz=ZoneInfo("UTC"))

    report = suite_report(empty_conn, repos=(REPO_A,), window=window, recording=True)

    assert {g["name"]: g["slowdown"]["before"] for g in report["gates"]} == dict.fromkeys(
        names, 10.0
    )


def test_suite_report_all_repos(empty_conn: sqlite3.Connection) -> None:
    """With every repo, the repo moves from the top level onto each gate."""
    insert(empty_conn, BASE + 100, "pass", duration=1.0)
    insert(empty_conn, BASE + 200, "pass", repo=REPO_B, duration=2.0)

    report = suite_report(empty_conn, repos=None, window=WINDOW, recording=True)

    assert (report["repo"], report["repo_name"]) == (None, None)
    assert [(g["repo"], g["repo_name"]) for g in report["gates"]] == [
        (REPO_B, "other"),
        (REPO_A, "proj"),
    ]


def test_suite_report_without_record() -> None:
    """No record gives zero totals and no gates, and says when recording is off."""
    report = suite_report(None, repos=(REPO_A,), window=WINDOW, recording=False)

    assert report["recording"] is False
    assert report["repo_name"] == "proj"
    assert report["gates"] == []
    assert set(report["totals"].values()) == {0}


def test_gate_report_recording_off(empty_conn: sqlite3.Connection) -> None:
    """The one-gate view says when recording is off, and says nothing when it is on."""
    insert(empty_conn, BASE + 100, "pass", duration=1.0)

    off = gate_report(
        empty_conn, repo=REPO_A, name="lint", window=WINDOW, limit=5, current=None,
        recording=False,
    )  # fmt: skip
    on = gate_report(
        empty_conn, repo=REPO_A, name="lint", window=WINDOW, limit=5, current=None, recording=True
    )

    assert off is not None
    assert on is not None
    assert off["recording"] is False
    assert "recording" not in on


def test_gate_report_caps(empty_conn: sqlite3.Connection) -> None:
    """Every capped list reports its total and shows at most the limit."""
    for i in range(30):
        insert(
            empty_conn, BASE + i, "fail" if i % 2 else "pass", duration=1.0, exit_code=1,
            raw={"branch": f"b{i}"},
        )  # fmt: skip

    report = gate_report(
        empty_conn, repo=REPO_A, name="lint", window=WINDOW, limit=5, current=None, recording=True
    )

    assert report is not None
    assert report["schema"] == REPORT_SCHEMA
    assert report["current"] is None
    assert (report["recent"]["total"], report["recent"]["shown"]) == (30, 5)
    assert len(report["recent"]["items"]) == 5
    assert report["recent"]["items"][0]["ts"] == "2023-11-14T00:00:29Z"
    (tree,) = report["flaky_trees"]["items"]
    assert (tree["tree"], tree["fails"], tree["passes"]) == ("t1", 15, 15)
    assert tree["last_seen"] == "2023-11-14T00:00:29Z"
    assert (tree["runs"]["total"], tree["runs"]["shown"]) == (30, 5)
    assert report["exit_codes"] == {"1": 15}
    assert report["trend"]["bucket"] == "day"
    assert report["variants"] == {"total": 0, "shown": 0, "items": []}
    assert (report["branches"]["total"], report["branches"]["shown"]) == (30, 5)
    assert len(report["branches"]["items"]) == 5
    assert (report["sources"]["total"], report["machines"]["total"]) == (1, 1)
    assert report["spot_checks"] is None


def test_gate_report_unknown(empty_conn: sqlite3.Connection) -> None:
    """A gate never recorded has no report; one recorded only before the window has a zero one."""
    insert(empty_conn, BASE - DAY, "pass", duration=1.0)

    assert (
        gate_report(
            empty_conn,
            repo=REPO_A,
            name="nope",
            window=WINDOW,
            limit=5,
            current=None,
            recording=True,
        )
        is None
    )
    report = gate_report(
        empty_conn, repo=REPO_A, name="lint", window=WINDOW, limit=5, current=None, recording=True
    )
    assert report is not None
    assert report["summary"]["runs"] == 0
    assert report["command"] == "lint"
    assert report["recent"] == {"total": 0, "shown": 0, "items": []}
    assert report["trend"]["items"] == []


def test_gate_report_current(empty_conn: sqlite3.Connection) -> None:
    """A plain gate's status is top level; a keyed gate's is on each variant, never on top."""
    insert(empty_conn, BASE + 100, "pass", name="test@py312", duration=1.0, paths=["tests"])
    insert(empty_conn, BASE + 200, "pass", name="test@py313", duration=1.0)
    insert(empty_conn, BASE + 300, "pass", name="lint", duration=1.0)
    insert(empty_conn, BASE - DAY, "pass", name="build@a", duration=1.0)
    insert(empty_conn, BASE + 400, "pass", name="build", duration=1.0)
    calls: list[tuple[str, list[str]]] = []

    def current(name: str, paths: Sequence[str]) -> dict[str, Any]:
        calls.append((name, list(paths)))
        return {"tree": f"tree-{name}", "result": "hit", "last_run": None}

    keyed = gate_report(
        empty_conn,
        repo=REPO_A,
        name="test",
        window=WINDOW,
        limit=5,
        current=current,
        recording=True,
    )
    plain = gate_report(
        empty_conn,
        repo=REPO_A,
        name="lint",
        window=WINDOW,
        limit=5,
        current=current,
        recording=True,
    )

    assert keyed is not None
    assert plain is not None
    assert keyed["current"] is None
    assert [(v["name"], v["current"]["tree"]) for v in keyed["variants"]["items"]] == [
        ("test@py313", "tree-test@py313"),
        ("test@py312", "tree-test@py312"),
    ]
    assert [v["last_run"] for v in keyed["variants"]["items"]] == [
        "2023-11-14T00:03:20Z",
        "2023-11-14T00:01:40Z",
    ]
    assert plain["current"]["tree"] == "tree-lint"

    assert calls == [("test@py313", ["src"]), ("test@py312", ["tests"]), ("lint", ["src"])]

    calls.clear()
    keyed_before_window = gate_report(
        empty_conn, repo=REPO_A, name="build", window=WINDOW, limit=5, current=current,
        recording=True,
    )  # fmt: skip
    assert keyed_before_window is not None
    assert keyed_before_window["current"] is None
    assert keyed_before_window["keyed"] is True
    assert plain["keyed"] is False
    assert calls == []

    text = render_gate(keyed_before_window, window=WINDOW)
    assert KEYED_STATUS in text
    assert UNKNOWN_STATUS not in text


# Per-test history reaches back 90 days from here, so the whole window is inside it.
TESTS_NOW = WINDOW.end


def _seed_tests(conn: sqlite3.Connection) -> None:
    """Record `test` with a flaky test, a retried test, and a run whose report was missing."""
    insert(conn, BASE + 100, "fail", name="test", tree="t1", duration=5.0)
    insert_results(conn, {"a": ("fail", 1.0), "b": ("pass", 2.0), "c": ("retried", 3.0)})
    insert(conn, BASE + 200, "pass", name="test", tree="t1", duration=6.0)
    insert_results(conn, {"a": ("pass", 1.0), "b": ("pass", 4.0), "c": ("pass", 3.0)})
    insert(conn, BASE + 300, "pass", name="test", tree="t2", duration=6.0, raw={"junit": "missing"})


def _gate(
    conn: sqlite3.Connection, name: str, *, limit: int = 5, now: float = TESTS_NOW
) -> dict[str, Any]:
    """Build the one-gate view of `name` in REPO_A over WINDOW."""
    report = gate_report(
        conn, repo=REPO_A, name=name, window=WINDOW, limit=limit, current=None, recording=True,
        now=now,
    )  # fmt: skip
    assert report is not None
    return report


def test_suite_report_tests(empty_conn: sqlite3.Connection) -> None:
    """Each gate counts its flaky and retried tests and report problems, or null without any."""
    _seed_tests(empty_conn)
    insert(empty_conn, BASE + 100, "pass", name="lint", duration=1.0)
    insert(empty_conn, BASE + 100, "pass", name="docs", duration=1.0, raw={"junit": "invalid"})

    report = suite_report(empty_conn, repos=(REPO_A,), window=WINDOW, recording=True, now=TESTS_NOW)

    tests = {gate["name"]: gate["tests"] for gate in report["gates"]}
    assert tests == {
        "test": {"flaky": 1, "retried": 1, "report_problems": 1},
        "docs": {"flaky": 0, "retried": 0, "report_problems": 1},
        "lint": None,
    }


def test_gate_report_tests(empty_conn: sqlite3.Connection) -> None:
    """The one-gate view lists slowest, flaky, and retried tests, capped, with report problems."""
    _seed_tests(empty_conn)

    report = _gate(empty_conn, "test", limit=2)

    tests = report["tests"]
    assert tests["since"] is None
    assert (tests["slowest"]["total"], tests["slowest"]["shown"]) == (3, 2)
    assert [t["name"] for t in tests["slowest"]["items"]] == ["b", "c"]
    assert set(tests["slowest"]["items"][0]) == {"name", "median", "runs", "share"}
    assert tests["flaky"]["items"] == [
        {"name": "a", "fails": 1, "passes": 1, "last_seen": "2023-11-14T00:03:20Z"}
    ]
    assert tests["retried"]["items"] == [
        {"name": "c", "runs": 1, "last_seen": "2023-11-14T00:01:40Z"}
    ]
    assert tests["report_problems"] == {"missing": 1, "stale": 0, "unreadable": 0}


@pytest.mark.parametrize(
    ("now", "since"),
    [
        pytest.param(TESTS_NOW, None, id="window inside retention"),
        pytest.param(TESTS_NOW + 365 * DAY, "2024-08-17T00:00:00Z", id="window reaches past"),
    ],
)
def test_gate_report_tests_since(
    empty_conn: sqlite3.Connection, now: float, since: str | None
) -> None:
    """`since` marks where per-test history starts when the window reaches further back."""
    _seed_tests(empty_conn)

    report = _gate(empty_conn, "test", now=now)

    assert report["tests"]["since"] == since


def test_gate_report_tests_null_without_test_data(empty_conn: sqlite3.Connection) -> None:
    """A gate with no test results and no report problem has no per-test section."""
    insert(empty_conn, BASE + 100, "pass", duration=1.0)

    report = _gate(empty_conn, "lint")

    assert report["tests"] is None


def test_run_failed_tests(empty_conn: sqlite3.Connection) -> None:
    """A failed run names its failed tests, capped; other runs and runs without results get null."""
    many = {f"t{i}": ("fail", 1.0) for i in range(FAILED_TESTS_SHOWN + 2)}
    insert(empty_conn, BASE + 100, "fail", name="test", duration=1.0)
    insert_results(empty_conn, many | {"ok": ("pass", 1.0)})
    insert(empty_conn, BASE + 200, "fail", name="test", duration=1.0)
    insert_results(empty_conn, {"ok": ("pass", 1.0)})
    insert(empty_conn, BASE + 300, "fail", name="test", duration=1.0)
    insert(empty_conn, BASE + 400, "pass", name="test", duration=1.0)
    insert_results(empty_conn, {"ok": ("pass", 1.0)})

    report = _gate(empty_conn, "test")

    passed, no_results, none_failed, capped = (
        run["failed_tests"] for run in report["recent"]["items"]
    )
    assert passed is None
    assert no_results is None
    assert none_failed == {"total": 0, "shown": 0, "items": []}
    assert capped == {
        "total": FAILED_TESTS_SHOWN + 2,
        "shown": FAILED_TESTS_SHOWN,
        "items": sorted(many)[:FAILED_TESTS_SHOWN],
    }
    (tree,) = report["flaky_trees"]["items"]
    assert [run["failed_tests"] for run in tree["runs"]["items"]][-1] == capped


def _seed_spot_checks(conn: sqlite3.Connection) -> None:
    """Record `test` with three failed spot checks, one passed, and a fail on a passing tree.

    `lint` runs one passing spot check, and another repo's `test` one failed spot check.
    """
    insert(conn, BASE + 100, "pass", name="test", duration=1.0)
    for i in range(3):
        insert(
            conn, BASE + 200 + i, "fail", name="test", duration=1.0, exit_code=1,
            spot_check=True,
        )  # fmt: skip
    insert_results(conn, {"a": ("fail", 1.0)})
    insert(conn, BASE + 300, "pass", name="test", duration=1.0, spot_check=True)
    insert(conn, BASE + 400, "pass", name="lint", duration=1.0, spot_check=True)
    insert(conn, BASE + 500, "fail", repo=REPO_B, name="test", duration=1.0, spot_check=True)


def test_suite_report_spot_checks(empty_conn: sqlite3.Connection) -> None:
    """Each gate counts its spot checks and dates the newest failure; failures are not flakes."""
    _seed_spot_checks(empty_conn)

    report = suite_report(empty_conn, repos=(REPO_A,), window=WINDOW, recording=True)

    gates = {gate["name"]: gate for gate in report["gates"]}
    assert gates["test"]["spot_checks"] == {
        "run": 4,
        "failed": 3,
        "last_failed": "2023-11-14T00:03:22Z",
    }
    assert gates["test"]["flaky"] is None
    assert gates["lint"]["spot_checks"] == {"run": 1, "failed": 0, "last_failed": None}
    assert (report["totals"]["spot_checks"], report["totals"]["spot_check_failures"]) == (5, 3)


def test_gate_report_spot_checks(empty_conn: sqlite3.Connection) -> None:
    """The one-gate view lists the gate's failed spot checks, newest first, capped."""
    _seed_spot_checks(empty_conn)

    report = _gate(empty_conn, "test", limit=2)

    spot = report["spot_checks"]
    assert (spot["run"], spot["failed"]) == (4, 3)
    assert (spot["failures"]["total"], spot["failures"]["shown"]) == (3, 2)
    newest, older = spot["failures"]["items"]
    assert [newest["ts"], older["ts"]] == ["2023-11-14T00:03:22Z", "2023-11-14T00:03:21Z"]
    assert newest["spot_check"] is True
    assert newest["failed_tests"] == {"total": 1, "shown": 1, "items": ["a"]}
    assert older["failed_tests"] is None
    assert "spot_checks" not in report["summary"]
    assert [run["spot_check"] for run in report["recent"]["items"]] == [True, True]


def test_report_problems_count_each_gate_recent_runs(empty_conn: sqlite3.Connection) -> None:
    """Each gate counts report problems in its own recent runs, not in the newest runs overall."""
    insert(empty_conn, BASE, "pass", name="docs", duration=1.0, raw={"junit": "stale"})
    for offset in range(1, REPORT_PROBLEM_RUNS + 1):
        insert(empty_conn, BASE + offset, "pass", name="lint", duration=1.0)

    report = suite_report(empty_conn, repos=(REPO_A,), window=WINDOW, recording=True, now=TESTS_NOW)

    tests = {gate["name"]: gate["tests"] for gate in report["gates"]}
    assert tests["docs"] == {"flaky": 0, "retried": 0, "report_problems": 1}


@pytest.mark.parametrize(
    ("repos", "text", "expected"),
    [
        pytest.param([REPO_A, REPO_B], "proj", REPO_A, id="display name"),
        pytest.param(["/a/shop/.git", "/b/shop/.git"], "shop (b)", "/b/shop/.git", id="label"),
        pytest.param(["/a/shop/.git", "/b/shop/.git"], "shop", AmbiguousRepoError, id="shared"),
        pytest.param([REPO_A], "missing", RepoNotFoundError, id="unknown"),
    ],
)
def test_resolve_repo_by_name(
    empty_conn: sqlite3.Connection, repos: list[str], text: str, expected: str | type[LookupError]
) -> None:
    """A name matches a display name or a work tree folder, and must match exactly one repo."""
    for i, repo in enumerate(repos):
        insert(empty_conn, BASE + i, "pass", repo=repo)

    if isinstance(expected, str):
        assert resolve_repo(empty_conn, text) == expected
    else:
        with pytest.raises(expected) as exc:
            resolve_repo(empty_conn, text)
        if isinstance(exc.value, AmbiguousRepoError):
            assert exc.value.matches == [("shop (a)", "/a/shop"), ("shop (b)", "/b/shop")]


def test_resolve_repo_by_path(empty_conn: sqlite3.Connection, git_repo: Path) -> None:
    """A folder or file inside a recorded repo resolves to that repo, wherever its folder sits."""
    common = str(git_common_dir(git_repo))
    insert(empty_conn, BASE, "pass", repo=common)
    (git_repo / "sub").mkdir()

    assert resolve_repo(empty_conn, str(git_repo / "sub")) == common
    assert resolve_repo(empty_conn, str(git_repo / "a.txt")) == common


def test_open_record_creates_nothing(stats_dirs: tuple[Path, Path]) -> None:
    """With no archive and no inbox, there is no record and no state directory appears."""
    state = stats_dirs[1]

    with open_record() as conn:
        assert conn is None
    assert not state.exists()


def _queue_event(state: Path) -> Path:
    """Write one settled event to the inbox and return the inbox."""
    state.mkdir(parents=True, exist_ok=True)
    inbox = state / INBOX_NAME
    # A recent ts, since ingest prunes events past retention.
    event = {
        "v": 1,
        "ts": time.time(),
        "name": "lint",
        "outcome": "pass",
        "paths": [],
        "repo": REPO_A,
    }
    inbox.write_text(json.dumps(event) + "\n", encoding="utf-8")
    settled = time.time() - 60
    os.utime(inbox, (settled, settled))
    return inbox


def test_open_record_ingests_pending_events(stats_dirs: tuple[Path, Path]) -> None:
    """The report reads events still waiting in the inbox."""
    _queue_event(stats_dirs[1])

    with open_record() as conn:
        assert conn is not None
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone() == (1,)


def test_open_record_reads_a_run_that_just_ended(stats_dirs: tuple[Path, Path]) -> None:
    """A run recorded a moment ago is in the report, before its inbox settles."""
    inbox = _queue_event(stats_dirs[1])
    now = time.time()
    os.utime(inbox, (now, now))

    with open_record() as conn:
        assert conn is not None
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone() == (1,)


def test_open_record_with_dashboard_lock(stats_dirs: tuple[Path, Path]) -> None:
    """While a dashboard holds the lock, the report reads without ingest and keeps its URL."""
    state = stats_dirs[1]
    Archive.open(state / ARCHIVE_NAME).close()
    lock = InstanceLock.acquire(state)
    assert lock is not None
    lock.write_url("http://127.0.0.1:1")
    inbox = _queue_event(state)
    try:
        with open_record() as conn:
            assert conn is not None
            assert conn.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)
        assert inbox.exists()
        assert running_url(state) == "http://127.0.0.1:1"
    finally:
        lock.release()
