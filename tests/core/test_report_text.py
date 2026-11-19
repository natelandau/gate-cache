"""Tests for the text form of the stats report."""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from gate_cache.stats.report import Window
from gate_cache.stats.report_text import (
    ALL_REPOS,
    FAILED_SPOT_CHECK_NOTE,
    FLAKY_NOTE,
    FLAKY_TESTS_NOTE,
    MORE_ITEMS,
    RECORDING_OFF_HINT,
    REPORT_HINT,
    REPORT_PROBLEMS_NOTE,
    RUN_FAILED_TESTS,
    SLOWDOWN_NOTE,
    SPAN,
    SPAN_TO_NOW,
    SPOT_CHECK_RUN,
    TESTS_SINCE,
)
from gate_cache.stats.report_text import render_gate as _render_gate
from gate_cache.stats.report_text import render_suite as _render_suite
from tests.conftest import rendered_text

UTC = ZoneInfo("UTC")
WINDOW = {"since": "2026-10-19T12:00:00Z", "until": "2026-11-18T12:00:00Z", "days": 30.0}
NOW = datetime.fromisoformat(WINDOW["until"]).timestamp()
SPAN_WINDOW = Window(start=datetime.fromisoformat(WINDOW["since"]).timestamp(), end=NOW, tz=UTC)
RUN = {
    "ts": "2026-11-17T09:02:11Z",
    "name": "test",
    "outcome": "fail",
    "exit_code": 137,
    "duration": 14.0,
    "tree": "a41c9e02b7d1",
    "commit": "9be21f4",
    "branch": "feat/x",
    "source": "agent",
    "agent": "claude",
    "machine": "a1b2c3",
    "spot_check": False,
    "failed_tests": {"total": 3, "shown": 2, "items": ["test_alpha", "test_beta"]},
}
SPOT_CHECK = RUN | {"spot_check": True, "branch": "spot/branch", "failed_tests": None}


def render_suite(report: dict[str, Any], **kwargs: Any) -> str:
    """Render the suite view and return the text a person sees."""
    return rendered_text(_render_suite(report, **kwargs))


def render_gate(report: dict[str, Any], **kwargs: Any) -> str:
    """Render the one-gate view and return the text a person sees."""
    return rendered_text(_render_gate(report, **kwargs))


def _capped(items: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    return {"total": len(items) if total is None else total, "shown": len(items), "items": items}


def _suite_gate(name: str, **overrides: Any) -> dict[str, Any]:
    gate = {
        "name": name,
        "command": name,
        "paths": [],
        "runs": 10,
        "skip_rate": 0.5,
        "failures": 1,
        "median_run": 12.0,
        "p90_run": 20.0,
        "time_spent": 120.0,
        "time_saved": 60.0,
        "fail_time": 5.0,
        "last_run": "2026-11-18T10:00:00Z",
        "flaky": None,
        "slowdown": None,
        "uncached": [],
        "waits": None,
        "tests": None,
        "spot_checks": None,
    }
    return gate | overrides


def _suite(**overrides: Any) -> dict[str, Any]:
    report = {
        "schema": 1,
        "repo": "/x/shop/.git",
        "repo_name": "shop",
        "window": WINDOW,
        "totals": {
            "runs": 20,
            "skips": 10,
            "time_saved": 120.0,
            "time_spent": 240.0,
            "fail_time": 10.0,
            "overhead": 1.0,
            "spot_checks": 2,
            "spot_check_failures": 1,
        },
        "gates": [
            _suite_gate(
                "test",
                flaky={"trees": 3, "fails": 5, "passes": 4, "last_seen": "2026-11-17T09:12:40Z"},
                slowdown={"before": 10.0, "now": 12.5, "change": 0.25},
                tests={"flaky": 2, "retried": 0, "report_problems": 1},
                spot_checks={"run": 2, "failed": 1, "last_failed": "2026-11-17T09:02:11Z"},
            ),
            _suite_gate("lint", median_run=None, p90_run=None),
        ],
    }
    return report | overrides


def _gate(**overrides: Any) -> dict[str, Any]:
    report = {
        "schema": 1,
        "repo": "/x/shop/.git",
        "repo_name": "shop",
        "name": "test",
        "command": "uv run pytest",
        "paths": ["src", "tests"],
        "variants": {"total": 0, "shown": 0, "items": []},
        "window": WINDOW,
        "keyed": False,
        "current": {"tree": "aaff74984ccc", "result": "miss", "last_run": None},
        "summary": {
            "runs": 3,
            "skip_rate": 0.0,
            "failures": 2,
            "median_run": 14.0,
            "p90_run": 14.0,
            "time_spent": 42.0,
            "time_saved": 0.0,
            "fail_time": 28.0,
            "cpu_ratio": 3.4,
            "peak_rss": 812_000_000,
            "median_rss": 640_000_000,
            "overhead": 0.2,
        },
        "trend": {
            "bucket": "day",
            "items": [{"start": "2026-11-17", "runs": 3, "median": 14.0, "p90": 14.0}],
        },
        "failure_timing": {
            "threshold": 7.0,
            "early": {"runs": 0, "time": 0.0},
            "late": {"runs": 2, "time": 28.0},
            "unclassified": {"runs": 0, "time": 0.0},
        },
        "exit_codes": {"137": 2},
        "sources": _capped(
            [{"source": "agent", "agent": "claude", "runs": 3, "failures": 2, "time_spent": 42.0}]
        ),
        "branches": _capped([{"branch": "feat/x", "runs": 3, "failures": 2}]),
        "machines": _capped([{"machine": "a1b2c3", "host": "laptop", "runs": 3, "failures": 2}]),
        "uncached": [],
        "waits": None,
        "flaky_trees": {
            "total": 1,
            "shown": 1,
            "items": [
                {
                    "tree": "a41c9e02b7d1",
                    "fails": 2,
                    "passes": 1,
                    "last_seen": "2026-11-17T09:12:40Z",
                    "runs": {"total": 1, "shown": 1, "items": [RUN]},
                }
            ],
        },
        "recent": {"total": 3, "shown": 1, "items": [RUN]},
        "spot_checks": {"run": 2, "failed": 1, "failures": _capped([SPOT_CHECK])},
        "tests": {
            "since": "2026-08-20T12:00:00Z",
            "slowest": _capped([{"name": "test_slow", "median": 4.0, "runs": 3, "share": 0.3}]),
            "flaky": _capped(
                [
                    {
                        "name": "test_flake",
                        "fails": 1,
                        "passes": 2,
                        "last_seen": "2026-11-17T09:12:40Z",
                    }
                ]
            ),
            "retried": _capped(
                [{"name": "test_retry", "runs": 2, "last_seen": "2026-11-17T09:12:40Z"}]
            ),
            "report_problems": {"missing": 1, "stale": 0, "unreadable": 0},
        },
    }
    return report | overrides


def test_render_suite() -> None:
    """The suite text names the repo and every gate, notes problems, and points at --name."""
    text = render_suite(_suite(), window=SPAN_WINDOW)

    assert "shop" in text
    assert "test" in text
    assert "lint" in text
    assert FLAKY_NOTE.format(trees="3 trees") in text
    assert SLOWDOWN_NOTE.format(percent=25) in text
    assert FLAKY_TESTS_NOTE.format(tests="2 tests") in text
    assert REPORT_PROBLEMS_NOTE in text
    assert FAILED_SPOT_CHECK_NOTE.format(count="1 spot check") in text
    assert REPORT_HINT in text
    assert RECORDING_OFF_HINT not in text


def test_render_suite_all_repos_names_each_repo() -> None:
    """Across every repo, the header says so and each gate row names its repo."""
    gates = [
        _suite_gate("test", repo="/x/shop/.git", repo_name="shop"),
        _suite_gate("test", repo="/x/cart/.git", repo_name="cart"),
    ]
    text = render_suite(_suite(repo=None, repo_name=None, gates=gates), window=SPAN_WINDOW)

    assert ALL_REPOS in text
    assert "shop" in text
    assert "cart" in text


@pytest.mark.parametrize(
    ("render", "build"),
    [
        (render_suite, lambda: _suite(recording=False)),
        (render_gate, lambda: _gate(recording=False)),
    ],
)
def test_render_recording_off_leads(
    render: Callable[..., str], build: Callable[[], dict[str, Any]]
) -> None:
    """With recording off, the first line says so and how to turn it on."""
    assert render(build(), window=SPAN_WINDOW).splitlines()[0].strip() == RECORDING_OFF_HINT


def test_render_gate() -> None:
    """The one-gate text shows the command, the status here, failures, and every run list."""
    text = render_gate(_gate(), window=SPAN_WINDOW)

    assert "uv run pytest" in text
    assert "aaff74984ccc" in text
    assert "137" in text
    assert "a41c9e02b7d1" in text
    assert "feat/x" in text
    assert "claude" in text
    assert "test_beta" in text
    for name in ("test_slow", "test_flake", "test_retry"):
        assert name in text
    assert TESTS_SINCE.format(day="Aug 20") in text
    assert "spot/branch" in text
    assert f"fail ({SPOT_CHECK_RUN})" in text
    assert REPORT_HINT not in text


def test_render_gate_skips_failed_tests_when_none_failed() -> None:
    """A failed run whose test results hold no failure shows no failed-test list."""
    run = RUN | {"failed_tests": {"total": 0, "shown": 0, "items": []}}
    report = _gate(recent={"total": 1, "shown": 1, "items": [run]}, spot_checks=None)
    text = render_gate(report, window=SPAN_WINDOW)

    assert RUN_FAILED_TESTS.format(names="") not in text


def test_render_gate_caps_long_lists() -> None:
    """A list cut to the limit shows its items and says how many of its total it left out."""
    branches = [{"branch": f"b{i}", "runs": 1, "failures": 0} for i in range(2)]

    text = render_gate(_gate(branches=_capped(branches, total=5)), window=SPAN_WINDOW, limit=2)

    assert "b1" in text
    assert MORE_ITEMS.format(count=3) in text


@pytest.mark.parametrize(
    ("since", "until", "ends_now", "expected"),
    [
        pytest.param(
            "2026-11-18T11:00:00Z",
            "2026-11-18T12:00:00Z",
            True,
            SPAN_TO_NOW.format(length="1 hour", since="Nov 18", until="Nov 18"),
            id="hours",
        ),
        pytest.param(
            "2026-11-11T12:00:00Z",
            "2026-11-18T12:00:00Z",
            True,
            SPAN_TO_NOW.format(length="7 days", since="Nov 11", until="Nov 18"),
            id="days",
        ),
        pytest.param(
            "2026-11-11T12:00:00Z",
            "2026-11-18T12:00:00Z",
            False,
            SPAN.format(length="7 days", since="Nov 11, 2026", until="Nov 18, 2026"),
            id="ends before now",
        ),
        pytest.param(
            "2025-12-28T12:00:00Z",
            "2026-01-04T12:00:00Z",
            True,
            SPAN_TO_NOW.format(length="7 days", since="Dec 28, 2025", until="Jan 4, 2026"),
            id="crosses a new year",
        ),
        pytest.param(
            "1970-01-01T00:00:00Z",
            "2026-11-18T12:00:00Z",
            True,
            SPAN_TO_NOW.format(length="56.9 years", since="Jan 1, 1970", until="Nov 18, 2026"),
            id="clamped to 1970",
        ),
    ],
)
@pytest.mark.parametrize("render", [render_suite, render_gate])
def test_render_window_span(
    render: Callable[..., str], since: str, until: str, ends_now: bool, expected: str
) -> None:
    """The header measures the window and dates it with years unless it ends now within a year."""
    window = Window(
        start=datetime.fromisoformat(since).timestamp(),
        end=datetime.fromisoformat(until).timestamp(),
        tz=UTC,
        ends_now=ends_now,
    )
    build = _suite if render is render_suite else _gate

    header = render(build(), window=window).splitlines()[0]

    assert f": {expected}" in header


@pytest.mark.parametrize(("zone", "day"), [("UTC", "Nov 18"), ("America/New_York", "Nov 17")])
def test_render_dates_in_the_report_zone(zone: str, day: str) -> None:
    """Dates fall on the days of the zone the report's trend uses, not the process zone."""
    window = Window(
        start=datetime.fromisoformat("2026-11-11T02:00:00Z").timestamp(),
        end=datetime.fromisoformat("2026-11-18T02:00:00Z").timestamp(),
        tz=ZoneInfo(zone),
    )

    header = render_suite(_suite(), window=window).splitlines()[0]

    assert f"to {day})" in header
