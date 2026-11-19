"""Render the `stats report` JSON contract as text for people.

Apart from the window, the renderers read only the contract's keys, so the text and the
JSON never disagree.
"""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import TYPE_CHECKING, Any

from gate_cache.console import format_duration, kv_text

if TYPE_CHECKING:
    from gate_cache.stats.report import Window

REPORT_HINT = "Run `gate-cache stats report --name GATE` for one gate."
RECORDING_OFF_HINT = (
    "Stats recording is off, so new runs are not recorded. Run `gate-cache stats on` to turn it on."
)
UNKNOWN_GATE = "no recorded run of gate {name!r} in {repo}"
UNKNOWN_STATUS = "unknown here"
KEYED_STATUS = "each key has its own status, see variants"
UNKNOWN_REPO = "no recorded repository matches {text!r}"
AMBIGUOUS_REPO = "{text!r} matches more than one repository; give --repo a path instead:"
KEYED_NAME_ERROR = "stats group keyed names under the gate; use --name {gate}"
ALL_REPOS = "all repos"
FAILED_SPOT_CHECK_NOTE = "{count} failed"
FLAKY_NOTE = "flaky on {trees}"
SLOWDOWN_NOTE = "median up {percent}%"
FLAKY_TESTS_NOTE = "{tests} flaky"
REPORT_PROBLEMS_NOTE = "test report problems"
TESTS_SINCE = "test history starts {day}"
RUN_FAILED_TESTS = "failed: {names}"
SPOT_CHECK_RUN = "spot check"
MORE_ITEMS = "... {count} more"
SPAN_TO_NOW = "last {length} ({since} to {until})"
SPAN = "{length} ({since} to {until})"

_NO_RUNS = "No gate ran in this window."
_HEADINGS = ("GATE", "RUNS", "SKIP", "FAIL", "MEDIAN", "P90", "SPENT", "NOTES")
_LEFT_COLUMNS = {"REPO", "GATE", "NOTES"}
_GAP = "  "
_KB = 1024
_TREE_LENGTH = 12
_DAY_SECONDS = 86400
_YEAR_DAYS = 365


def _local(ts: str, tz: tzinfo) -> datetime:
    return datetime.fromisoformat(ts).astimezone(tz)


def _day(moment: datetime) -> str:
    return f"{moment:%b} {moment.day}"


def _plural(count: float, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _runs(count: int) -> str:
    return _plural(count, "run")


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    return "0s" if seconds == 0 else format_duration(seconds)


def _percent(ratio: float | None) -> str:
    return "-" if ratio is None else f"{round(ratio * 100)}%"


def _bytes(count: float | None) -> str:
    if count is None:
        return "-"
    value = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if value < _KB:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= _KB
    return f"{value:.1f} TB"


def _length(seconds: float) -> str:
    # A year is 365 days, as `--since 1y` counts it.
    if seconds < _DAY_SECONDS:
        unit, noun = 3600, "hour"
    elif seconds < _YEAR_DAYS * _DAY_SECONDS:
        unit, noun = _DAY_SECONDS, "day"
    else:
        unit, noun = _YEAR_DAYS * _DAY_SECONDS, "year"
    value = round(seconds / unit, 1)
    return _plural(int(value) if value == int(value) else value, noun)


def _span(window: Window) -> str:
    """Return the window as text, with years on its dates unless it ends now within one year."""
    since = datetime.fromtimestamp(window.start, window.tz)
    until = datetime.fromtimestamp(window.end, window.tz)
    length = _length(window.end - window.start)
    if window.ends_now and since.year == until.year:
        return SPAN_TO_NOW.format(length=length, since=_day(since), until=_day(until))
    dates = {"since": f"{_day(since)}, {since:%Y}", "until": f"{_day(until)}, {until:%Y}"}
    return (SPAN_TO_NOW if window.ends_now else SPAN).format(length=length, **dates)


def _lead(report: dict[str, Any]) -> list[str]:
    return [RECORDING_OFF_HINT] if report.get("recording") is False else []


def _table(rows: list[list[str]], headings: list[str]) -> list[str]:
    widths = [max(len(row[i]) for row in [headings, *rows]) for i in range(len(headings))]
    lines = []
    for row in [headings, *rows]:
        cells = [
            cell.ljust(width) if heading in _LEFT_COLUMNS else cell.rjust(width)
            for cell, width, heading in zip(row, widths, headings, strict=True)
        ]
        lines.append(_GAP.join(cells).rstrip())
    return lines


def _notes(gate: dict[str, Any]) -> str:
    notes = []
    if (spot := gate["spot_checks"]) and spot["failed"]:
        notes.append(FAILED_SPOT_CHECK_NOTE.format(count=_plural(spot["failed"], "spot check")))
    if gate["flaky"] is not None:
        notes.append(FLAKY_NOTE.format(trees=_plural(gate["flaky"]["trees"], "tree")))
    if gate["slowdown"] is not None:
        notes.append(SLOWDOWN_NOTE.format(percent=round(gate["slowdown"]["change"] * 100)))
    if tests := gate["tests"]:
        if tests["flaky"]:
            notes.append(FLAKY_TESTS_NOTE.format(tests=_plural(tests["flaky"], "test")))
        if tests["report_problems"]:
            notes.append(REPORT_PROBLEMS_NOTE)
    return ", ".join(notes)


def render_suite(report: dict[str, Any], *, window: Window) -> str:
    """Render the suite view as a header line, one table row per gate, and a hint.

    Args:
        report: The suite view of the report contract.
        window: Time range of the report; its zone dates the text, as it buckets the trend.

    Returns:
        str: The text, ending in a newline.
    """
    totals = report["totals"]
    scope = f"{report['repo_name'] or ALL_REPOS}: {_span(window)}"
    cost = (
        f"{_runs(totals['runs'])}, {_duration(totals['time_saved'])} saved, "
        f"{_duration(totals['time_spent'])} spent"
    )
    lines = [*_lead(report), f"{scope}{_GAP * 2}{cost}", ""]
    gates = report["gates"]
    if not gates:
        lines.append(_NO_RUNS)
        return "\n".join(lines) + "\n"
    with_repo = report["repo"] is None
    headings = ["REPO", *_HEADINGS] if with_repo else list(_HEADINGS)
    rows = [
        [
            *([gate["repo_name"] or "-"] if with_repo else []),
            gate["name"],
            str(gate["runs"]),
            _percent(gate["skip_rate"]),
            str(gate["failures"]),
            _duration(gate["median_run"]),
            _duration(gate["p90_run"]),
            _duration(gate["time_spent"]),
            _notes(gate),
        ]
        for gate in gates
    ]
    lines.extend([*_table(rows, headings), "", REPORT_HINT])
    return "\n".join(lines) + "\n"


def _block(title: str, rows: dict[str, str]) -> list[str]:
    return ["", title, kv_text(rows).rstrip("\n")] if rows else []


def _list(title: str, items: list[str], *, total: int | None = None, limit: int) -> list[str]:
    """Return a titled list of at most `limit` items, counting the rest on a last line."""
    if not items:
        return []
    shown = items[:limit]
    left = (len(items) if total is None else total) - len(shown)
    more = [MORE_ITEMS.format(count=left)] if left > 0 else []
    return ["", title, *(f"  {item}" for item in [*shown, *more])]


def _current(status: dict[str, Any] | None) -> str:
    if status is None:
        return UNKNOWN_STATUS
    text = f"{status['result']} on {status['tree'][:_TREE_LENGTH]}"
    if (last := status.get("last_run")) and last.get("exit_code") is not None:
        text += f" (last run exit code {last['exit_code']})"
    return text


def _run_line(run: dict[str, Any], tz: tzinfo) -> str:
    exit_code = f" exit {run['exit_code']}" if run["exit_code"] else ""
    where = " ".join(
        part for part in (run["branch"], run["commit"], _who(run["source"], run["agent"])) if part
    )
    ts = _local(run["ts"], tz)
    outcome = f"{run['outcome']} ({SPOT_CHECK_RUN})" if run["spot_check"] else run["outcome"]
    line = f"{_day(ts)} {ts:%H:%M}  {outcome}{exit_code}  {_duration(run['duration'])}  {where}"
    if (failed := run["failed_tests"]) and failed["total"]:
        names = ", ".join(failed["items"])
        left = failed["total"] - failed["shown"]
        line += "  " + RUN_FAILED_TESTS.format(names=names) + (f" (+{left})" if left else "")
    return line


def _who(source: str | None, agent: str | None) -> str:
    if source is None:
        return ""
    return f"{source} ({agent})" if agent else source


def _summary(summary: dict[str, Any]) -> dict[str, str]:
    rows = {
        "runs": str(summary["runs"]),
        "skip rate": _percent(summary["skip_rate"]),
        "failures": str(summary["failures"]),
        "median run": _duration(summary["median_run"]),
        "p90 run": _duration(summary["p90_run"]),
        "time spent": _duration(summary["time_spent"]),
        "time saved": _duration(summary["time_saved"]),
        "fail time": _duration(summary["fail_time"]),
        "overhead": _duration(summary["overhead"]),
    }
    if summary["cpu_ratio"] is not None:
        rows["cpu"] = f"{summary['cpu_ratio']:.1f}x wall time"
    if summary["peak_rss"] is not None:
        rows["memory"] = (
            f"{_bytes(summary['median_rss'])} median, {_bytes(summary['peak_rss'])} peak"
        )
    return rows


def _failures(report: dict[str, Any]) -> dict[str, str]:
    rows: dict[str, str] = {}
    if report["exit_codes"]:
        rows["exit codes"] = ", ".join(
            f"{code} ({count})" for code, count in report["exit_codes"].items()
        )
    timing = report["failure_timing"]
    parts = [
        f"{key} {timing[key]['runs']} ({_duration(timing[key]['time'])})"
        for key in ("early", "late", "unclassified")
        if timing[key]["runs"]
    ]
    if parts:
        threshold = timing["threshold"]
        rows["timing"] = ", ".join(parts)
        if threshold is not None:
            rows["timing"] += f"; early means under {_duration(threshold)}"
    return rows


def _waits(waits: dict[str, Any] | None) -> dict[str, str]:
    if waits is None:
        return {}
    return {
        "waited": f"{_runs(waits['waited'])}, {_duration(waits['total_wait'])} in all, "
        f"{_duration(waits['median_wait'])} median",
        "then": f"{waits['skipped']} skipped, {waits['reported']} reported a failure, "
        f"{waits['ran']} ran, {waits['timed_out']} timed out",
    }


def _test_lines(tests: dict[str, Any] | None, tz: tzinfo, limit: int) -> list[str]:
    if tests is None:
        return []
    slowest = [
        f"{t['name']}: {_duration(t['median'])} median"
        + (f", {_percent(t['share'])} of a passing run" if t["share"] is not None else "")
        for t in tests["slowest"]["items"]
    ]
    flaky = [
        f"{t['name']}: {t['fails']} failed, {t['passes']} passed, last {_day(_local(t['last_seen'], tz))}"
        for t in tests["flaky"]["items"]
    ]
    retried = [
        f"{t['name']}: passed on retry in {_runs(t['runs'])}, last {_day(_local(t['last_seen'], tz))}"
        for t in tests["retried"]["items"]
    ]
    lines = _list("slowest tests", slowest, total=tests["slowest"]["total"], limit=limit)
    lines += _list("flaky tests", flaky, total=tests["flaky"]["total"], limit=limit)
    lines += _list("retried tests", retried, total=tests["retried"]["total"], limit=limit)
    lines += _block(
        "recent runs with test report problems",
        {kind: _runs(count) for kind, count in tests["report_problems"].items() if count},
    )
    if lines and tests["since"] is not None:
        lines += ["", TESTS_SINCE.format(day=_day(_local(tests["since"], tz)))]
    return lines


def render_gate(report: dict[str, Any], *, window: Window, limit: int = 20) -> str:
    """Render the one-gate view as a header and a short labeled block per section.

    Args:
        report: The one-gate view of the report contract.
        window: Time range of the report; its zone dates the text, as it buckets the trend.
        limit: Most rows any list shows; the JSON caps its own lists the same way.

    Returns:
        str: The text, ending in a newline.
    """
    variants = report["variants"]
    tz = window.tz
    span = _span(window)
    lines = [
        *_lead(report),
        f"{report['name']} in {report['repo_name']}: {span}",
        kv_text(
            {
                "command": report["command"] or "-",
                "paths": ", ".join(report["paths"]) or "whole tree",
                **(
                    {}
                    if variants["total"]
                    else {
                        "status": KEYED_STATUS if report["keyed"] else _current(report["current"])
                    }
                ),
            }
        ).rstrip("\n"),
    ]
    variant_lines = [
        f"{v['name']}: {_runs(v['runs'])}, last {_day(_local(v['last_run'], tz))}, {_current(v['current'])}"
        for v in variants["items"]
    ]
    lines += _list("variants", variant_lines, total=variants["total"], limit=limit)
    lines += _block("summary", _summary(report["summary"]))
    # The newest buckets matter most, so a long trend keeps its tail.
    trend = report["trend"]["items"][-limit:]
    lines += _block(
        f"trend by {report['trend']['bucket']}",
        {
            t["start"]: f"{_runs(t['runs'])}, median {_duration(t['median'])}, "
            f"p90 {_duration(t['p90'])}"
            for t in trend
        },
    )
    lines += _block("failures", _failures(report))
    dimensions = {
        "sources": [
            f"{_who(s['source'], s['agent'])}: {_runs(s['runs'])}, {s['failures']} failed, "
            f"{_duration(s['time_spent'])} spent"
            for s in report["sources"]["items"]
        ],
        "branches": [
            f"{b['branch'] or '-'}: {_runs(b['runs'])}, {b['failures']} failed"
            for b in report["branches"]["items"]
        ],
        "machines": [
            f"{m['host'] or m['machine'] or '-'}: {_runs(m['runs'])}, {m['failures']} failed"
            for m in report["machines"]["items"]
        ],
    }
    for title, items in dimensions.items():
        lines += _list(title, items, total=report[title]["total"], limit=limit)
    uncached = [
        f"{u['reason'] or '-'} ({u['outcome']}): {_runs(u['count'])}" for u in report["uncached"]
    ]
    lines += _list("ran without the cache", uncached, limit=limit)
    lines += _block("waits", _waits(report["waits"]))
    flaky = report["flaky_trees"]
    tree_lines = [
        f"{t['tree'][:_TREE_LENGTH]}: {t['fails']} failed, {t['passes']} passed, last {_day(_local(t['last_seen'], tz))}"
        for t in flaky["items"]
    ]
    lines += _list("flaky trees", tree_lines, total=flaky["total"], limit=limit)
    lines += _test_lines(report["tests"], tz, limit)
    if spot := report["spot_checks"]:
        failures = spot["failures"]
        lines += _block("spot checks", {"run": str(spot["run"]), "failed": str(spot["failed"])})
        lines += _list(
            "failed spot checks",
            [_run_line(r, tz) for r in failures["items"]],
            total=failures["total"],
            limit=limit,
        )
    recent = report["recent"]
    runs = [_run_line(r, tz) for r in recent["items"]]
    lines += _list("recent runs", runs, total=recent["total"], limit=limit)
    return "\n".join(lines) + "\n"
