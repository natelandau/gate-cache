"""Read per-test results from a JUnit XML report."""

from __future__ import annotations

import json
import math
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from gate_cache.safe_files import PRIVATE_DIR_MODE, ensure_private_dir, open_regular

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

TestOutcome = Literal["pass", "fail", "skip", "retried"]
# Name, outcome, and seconds the test took (None when the report gives no usable time).
TestResult = tuple[str, TestOutcome, float | None]
ReportStatus = Literal["missing", "stale", "invalid"]
# Worst first: an unparsable report is a bug to fix, a missing one may be expected.
_STATUS_RANK: tuple[ReportStatus, ...] = ("invalid", "stale", "missing")

MAX_REPORT_BYTES = 50 * 1024 * 1024
MAX_TESTS = 50_000
TESTS_DIR_NAME = "tests"
# File mtimes come from a coarser kernel clock than time.time_ns(), and some filesystems round to
# whole seconds, so a fresh report can look slightly older than the run start.
MTIME_TOLERANCE_NS = 2_000_000_000
NAME_SEPARATOR = "::"

_FAIL_TAGS = frozenset({"failure", "error"})
_RETRY_TAGS = frozenset({"rerunFailure", "rerunError", "flakyFailure", "flakyError"})


class ReportError(Exception):
    """A report could not be read as JUnit XML."""


def _result(elem: ET.Element) -> TestResult | None:
    name = elem.get("name")
    if not name:
        return None
    if classname := elem.get("classname"):
        name = f"{classname}{NAME_SEPARATOR}{name}"

    tags = {child.tag for child in elem}
    outcome: TestOutcome
    if tags & _FAIL_TAGS:
        outcome = "fail"
    elif "skipped" in tags:
        outcome = "skip"
    elif tags & _RETRY_TAGS:
        outcome = "retried"
    else:
        outcome = "pass"

    duration: float | None
    try:
        duration = float(elem.get("time", ""))
    except ValueError:
        duration = None
    if duration is not None and (not math.isfinite(duration) or duration < 0):
        duration = None
    return name, outcome, duration


def parse_report(path: Path) -> list[TestResult]:
    """Read every test case from a JUnit XML report.

    Args:
        path: The report file.

    Returns:
        One result per `<testcase>`, in document order. Attempts of the same test stay separate.

    Raises:
        ReportError: When the file is not a regular file, is unreadable or over the size cap, or
            cannot be parsed.
    """
    results: list[TestResult] = []
    try:
        # Close the file ourselves: an iterparse iterator left unexhausted on an error
        # keeps its own file open.
        with open_regular(path, max_bytes=MAX_REPORT_BYTES) as handle:
            open_elems: list[ET.Element] = []
            for event, elem in ET.iterparse(handle, events=("start", "end")):  # noqa: S314
                if event == "start":
                    open_elems.append(elem)
                    continue
                open_elems.pop()
                if elem.tag == "testcase" and (result := _result(elem)) is not None:
                    results.append(result)
                # Detach every finished element outside a test case, so memory stays flat however
                # many cases and suite outputs the report has. A case keeps its children for _result.
                if open_elems and open_elems[-1].tag != "testcase":
                    open_elems[-1].remove(elem)
    except (ET.ParseError, OSError, ValueError, RecursionError) as exc:
        raise ReportError(str(exc)) from exc
    return results


def collapse(results: Iterable[TestResult]) -> list[TestResult]:
    """Merge repeated attempts of a test into one result.

    Args:
        results: Results in run order, possibly with several attempts per name.

    Returns:
        One result per name in first-seen order. A test that failed and then passed is
        `retried`. The duration is the last attempt's.
    """
    attempts: dict[str, list[TestResult]] = {}
    for result in results:
        attempts.setdefault(result[0], []).append(result)

    collapsed: list[TestResult] = []
    for name, group in attempts.items():
        _, final, duration = group[-1]
        if final in ("pass", "retried") and any(
            outcome in ("fail", "retried") for _, outcome, _ in group
        ):
            final = "retried"
        collapsed.append((name, final, duration))
    return collapsed


@dataclass(frozen=True)
class ReportSnapshot:
    """Report files as they stood before the command ran."""

    targets: tuple[Path, ...]
    started_ns: int
    # Inode, mtime in ns, and size of each file seen.
    before: dict[Path, tuple[int, int, int]]


@dataclass(frozen=True)
class ReportRead:
    """Results from fresh reports, or why there are none."""

    results: list[TestResult]
    status: ReportStatus | None
    # The worst problem among the reports left unread, when others were read.
    problem: ReportStatus | None = None


def _candidates(target: Path) -> list[Path]:
    """List the report files a target names: itself, or the `*.xml` files directly in a folder."""
    try:
        if target.is_dir():
            return sorted(target.glob("*.xml"))
    except OSError:
        return []
    return [target]


def _signature(path: Path) -> tuple[int, int, int] | None:
    try:
        info = path.stat()
    except OSError:
        return None
    return info.st_ino, info.st_mtime_ns, info.st_size


def snapshot_reports(targets: Sequence[Path]) -> ReportSnapshot:
    """Record the report files that exist before the command runs.

    Comparing against this snapshot keeps a leftover report from an earlier run out of the stats.

    Args:
        targets: Report files or folders of reports.
    """
    started_ns = time.time_ns()
    before: dict[Path, tuple[int, int, int]] = {}
    for target in targets:
        for path in _candidates(target):
            if (sig := _signature(path)) is not None:
                before[path] = sig
    return ReportSnapshot(targets=tuple(targets), started_ns=started_ns, before=before)


def read_reports(snapshot: ReportSnapshot) -> ReportRead:
    """Read the reports the command wrote, and none that it did not.

    A report counts only when it is new or changed since the snapshot and was modified no
    earlier than the snapshot, less a small clock tolerance. Nothing is raised for a missing,
    stale, or invalid report.

    Args:
        snapshot: The state taken before the command ran.

    Returns:
        The merged results. With no results, the status says why. With results, the problem
        names the worst status of the targets that gave none, or of any invalid report.
    """
    reads = [_read_target(target, snapshot) for target in snapshot.targets]
    worst = _worst(status for _, status, _ in reads)
    if any(read for _, _, read in reads):
        results = [result for found, _, _ in reads for result in found]
        return ReportRead(results=collapse(results), status=None, problem=worst)
    return ReportRead(results=[], status=worst or "missing")


def _worst(statuses: Iterable[ReportStatus | None]) -> ReportStatus | None:
    """Return the worst of the statuses, or None when there are none."""
    seen = set(statuses)
    return next((status for status in _STATUS_RANK if status in seen), None)


def _read_target(
    target: Path, snapshot: ReportSnapshot
) -> tuple[list[TestResult], ReportStatus | None, bool]:
    """Read the reports one target names.

    Returns:
        The results, the worst problem among its reports, and whether any report was read.
    """
    paths = _candidates(target)
    if not paths:
        return [], "missing", False
    results: list[TestResult] = []
    statuses: set[ReportStatus | None] = set()
    read = False
    for path in paths:
        status, parsed = _read_one(path, snapshot)
        statuses.add(status)
        if parsed is not None:
            results.extend(parsed)
            read = True
    if read:
        # Old files beside a fresh report in a folder are earlier runs' output, not a problem.
        statuses &= {"invalid"}
    return results, _worst(statuses), read


def _read_one(
    path: Path, snapshot: ReportSnapshot
) -> tuple[ReportStatus | None, list[TestResult] | None]:
    """Parse one report if this run wrote it, else say why not."""
    sig = _signature(path)
    if sig is None:
        return "missing", None
    if sig == snapshot.before.get(path) or sig[1] < snapshot.started_ns - MTIME_TOLERANCE_NS:
        return "stale", None
    try:
        return None, parse_report(path)
    except ReportError:
        return "invalid", None


def write_results(event_id: str, results: Sequence[TestResult], *, state: Path) -> tuple[int, bool]:
    """Write a run's per-test results to its own file in the stats directory.

    Args:
        event_id: The run's id, used as the file name.
        results: The results to keep.
        state: The stats data directory.

    Returns:
        The number of results written, and whether the list was cut at `MAX_TESTS`.
    """
    if event_id in ("", ".", "..") or "/" in event_id or "\\" in event_id:
        msg = f"event_id must be a plain file name, got {event_id!r}"
        raise ValueError(msg)
    kept = list(results[:MAX_TESTS])
    folder = state / TESTS_DIR_NAME
    ensure_private_dir(state)
    folder.mkdir(mode=PRIVATE_DIR_MODE, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=folder, prefix=f".{event_id}.", suffix=".tmp", delete=False, encoding="utf-8"
    ) as tmp:
        tmp_path = Path(tmp.name)
        try:
            json.dump([list(result) for result in kept], tmp)
            tmp.flush()
            tmp_path.replace(folder / f"{event_id}.json")
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
    return len(kept), len(results) > len(kept)
