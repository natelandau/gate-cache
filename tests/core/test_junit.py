"""Tests for parsing JUnit XML reports."""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Literal

import pytest

from gate_cache.stats import junit

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path


def _write(tmp_path: Path, xml: str) -> Path:
    path = tmp_path / "report.xml"
    path.write_text(xml)
    return path


@pytest.mark.parametrize(
    ("body", "outcome"),
    [
        ("<failure/>", "fail"),
        ("<error/>", "fail"),
        ("<skipped/>", "skip"),
        ("", "pass"),
        ("<rerunFailure/>", "retried"),
        ("<rerunError/>", "retried"),
        ("<flakyFailure/>", "retried"),
        ("<flakyError/>", "retried"),
        ("<failure/><rerunFailure/>", "fail"),
    ],
)
def test_parse_maps_outcomes(tmp_path: Path, body: str, outcome: junit.TestOutcome) -> None:
    """A test case's child tags decide its outcome."""
    path = _write(tmp_path, f'<testsuite><testcase name="t">{body}</testcase></testsuite>')

    assert junit.parse_report(path) == [("t", outcome, None)]


def test_parse_names_and_durations(tmp_path: Path) -> None:
    """Names join class and test; an unusable time is None; a nameless case is dropped."""
    path = _write(
        tmp_path,
        (
            "<testsuite>"
            '<testcase classname="pkg.mod" name="test_a" time="1.5"/>'
            '<testcase name="test_b" time="abc"/>'
            '<testcase classname="pkg" name="test_c"/>'
            '<testcase name="n1" time="nan"/>'
            '<testcase name="n2" time="inf"/>'
            '<testcase name="n3" time="-1"/>'
            '<testcase classname="pkg" time="2"/>'
            "</testsuite>"
        ),
    )

    assert junit.parse_report(path) == [
        ("pkg.mod::test_a", "pass", 1.5),
        ("test_b", "pass", None),
        ("pkg::test_c", "pass", None),
        ("n1", "pass", None),
        ("n2", "pass", None),
        ("n3", "pass", None),
    ]


@pytest.mark.parametrize(
    "xml",
    [
        (
            '<testsuites><testsuite><testcase name="a"/></testsuite>'
            '<testsuite><testcase name="b"/></testsuite></testsuites>'
        ),
        '<testsuite><testcase name="a"/><testcase name="b"/></testsuite>',
        '<testsuite><testsuite><testcase name="a"/></testsuite><testcase name="b"/></testsuite>',
    ],
)
def test_parse_accepts_suite_shapes(tmp_path: Path, xml: str) -> None:
    """Every test case is found under any suite nesting."""
    names = [name for name, _, _ in junit.parse_report(_write(tmp_path, xml))]

    assert sorted(names) == ["a", "b"]


def test_parse_rejects_malformed_xml(tmp_path: Path) -> None:
    """Invalid XML is a report error, not a crash."""
    with pytest.raises(junit.ReportError):
        junit.parse_report(_write(tmp_path, "<testsuite><testcase"))


def test_parse_rejects_oversized_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A report over the size cap is rejected before parsing."""
    monkeypatch.setattr(junit, "MAX_REPORT_BYTES", 100)
    path = _write(tmp_path, "<testsuite>" + '<testcase name="a"/>' * 20 + "</testsuite>")

    with pytest.raises(junit.ReportError):
        junit.parse_report(path)


def test_parse_rejects_missing_file(tmp_path: Path) -> None:
    """An unreadable file is a report error."""
    with pytest.raises(junit.ReportError):
        junit.parse_report(tmp_path / "nope.xml")


@pytest.mark.parametrize("error", [ValueError("bad value"), RecursionError("too deep")])
def test_parse_wraps_parser_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """An error the XML parser raises while reading becomes a report error."""

    def fail(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(junit.ET, "iterparse", fail)

    with pytest.raises(junit.ReportError):
        junit.parse_report(_write(tmp_path, _case("a")))


def test_parse_releases_finished_elements(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Finished cases and suite-level outputs leave the tree, so memory stays flat."""
    roots: list[ET.Element] = []
    iterparse = ET.iterparse

    def spy(
        source: Path, events: Sequence[Literal["start", "end"]]
    ) -> Iterator[tuple[str, ET.Element]]:
        for event, elem in iterparse(source, events=events):
            if not roots:
                roots.append(elem)
            yield event, elem

    monkeypatch.setattr(junit.ET, "iterparse", spy)
    path = _write(
        tmp_path,
        (
            "<testsuites><testsuite>"
            '<properties><property name="p" value="v"/></properties>'
            '<testcase name="a"><system-out>out</system-out></testcase>'
            "<system-out>suite out</system-out><system-err>suite err</system-err>"
            "</testsuite></testsuites>"
        ),
    )

    assert junit.parse_report(path) == [("a", "pass", None)]
    assert list(roots[0]) == []


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [
        (["pass", "pass"], "pass"),
        (["fail", "pass"], "retried"),
        (["pass", "fail"], "fail"),
        (["fail", "fail"], "fail"),
        (["fail", "skip"], "skip"),
        (["retried"], "retried"),
    ],
)
def test_collapse(outcomes: list[junit.TestOutcome], expected: junit.TestOutcome) -> None:
    """Repeated attempts merge into one outcome with the last duration."""
    results: list[junit.TestResult] = [("t", o, float(i)) for i, o in enumerate(outcomes)]

    assert junit.collapse(results) == [("t", expected, float(len(outcomes) - 1))]


def test_collapse_keeps_first_seen_order() -> None:
    """Collapsed results keep the order names first appeared in."""
    results: list[junit.TestResult] = [("b", "pass", 1.0), ("a", "pass", 2.0), ("b", "pass", 3.0)]

    assert junit.collapse(results) == [("b", "pass", 3.0), ("a", "pass", 2.0)]


def _case(name: str) -> str:
    return f'<testsuite><testcase name="{name}"/></testsuite>'


def _set_mtime(path: Path, ns: int) -> None:
    os.utime(path, ns=(ns, ns))


def _write_fresh(path: Path, xml: str, snap: junit.ReportSnapshot) -> None:
    """Write a report as the run would, with an explicit mtime after the run start."""
    path.write_text(xml)
    _set_mtime(path, snap.started_ns + 1_000)


def test_report_written_during_run_is_read(tmp_path: Path) -> None:
    """A report that did not exist before the run is read."""
    report = tmp_path / "r.xml"
    snap = junit.snapshot_reports([report])
    _write_fresh(report, _case("a"), snap)

    read = junit.read_reports(snap)

    assert read.results == [("a", "pass", None)]
    assert read.status is None


def test_unchanged_report_is_stale(tmp_path: Path) -> None:
    """A report the run did not touch is never read."""
    report = tmp_path / "r.xml"
    report.write_text(_case("a"))
    snap = junit.snapshot_reports([report])

    read = junit.read_reports(snap)

    assert read.results == []
    assert read.status == "stale"


def test_missing_report(tmp_path: Path) -> None:
    """A report that never appears is missing."""
    snap = junit.snapshot_reports([tmp_path / "r.xml"])

    assert junit.read_reports(snap).status == "missing"


def test_rewritten_report_is_read(tmp_path: Path) -> None:
    """A report rewritten with new content during the run is read."""
    report = tmp_path / "r.xml"
    report.write_text(_case("old"))
    _set_mtime(report, 1)
    snap = junit.snapshot_reports([report])
    report.write_text(_case("new-name"))

    assert junit.read_reports(snap).results == [("new-name", "pass", None)]


def test_report_changed_but_older_than_run_is_stale(tmp_path: Path) -> None:
    """A changed file whose mtime predates the run start is not this run's output."""
    report = tmp_path / "r.xml"
    report.write_text(_case("old"))
    snap = junit.snapshot_reports([report])
    report.write_text(_case("different"))
    _set_mtime(report, snap.started_ns - junit.MTIME_TOLERANCE_NS - 1_000_000)

    assert junit.read_reports(snap).status == "stale"


def test_folder_reads_only_new_or_changed_files(tmp_path: Path) -> None:
    """A folder target reads only fresh XML files directly inside it."""
    folder = tmp_path / "reports"
    folder.mkdir()
    (folder / "TEST-old.xml").write_text(_case("old"))
    snap = junit.snapshot_reports([folder])
    assert junit.read_reports(snap).status == "stale"

    _write_fresh(folder / "TEST-new.xml", _case("new"), snap)
    (folder / "sub").mkdir()
    _write_fresh(folder / "sub" / "TEST-deep.xml", _case("deep"), snap)

    assert junit.read_reports(snap).results == [("new", "pass", None)]


def test_missing_folder(tmp_path: Path) -> None:
    """A folder target that does not exist is missing."""
    snap = junit.snapshot_reports([tmp_path / "nope"])

    assert junit.read_reports(snap).status == "missing"


def test_invalid_report(tmp_path: Path) -> None:
    """A fresh report that cannot be parsed is invalid."""
    report = tmp_path / "r.xml"
    snap = junit.snapshot_reports([report])
    _write_fresh(report, "<testsuite>", snap)

    read = junit.read_reports(snap)

    assert read.results == []
    assert read.status == "invalid"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs named pipes")
def test_report_that_is_not_a_regular_file_is_invalid(tmp_path: Path) -> None:
    """A named pipe is never opened, so it cannot block the run, and counts as invalid."""
    report = tmp_path / "r.xml"
    snap = junit.snapshot_reports([report])
    os.mkfifo(report)

    assert junit.read_reports(snap).status == "invalid"


def test_partial_read_names_the_worst_unread_problem(tmp_path: Path) -> None:
    """Results from one target still note the worst problem among the targets left unread."""
    good, stale, gone = tmp_path / "good.xml", tmp_path / "s.xml", tmp_path / "g.xml"
    stale.write_text(_case("old"))
    snap = junit.snapshot_reports([good, stale, gone])
    _write_fresh(good, _case("a"), snap)

    read = junit.read_reports(snap)

    assert read.results == [("a", "pass", None)]
    assert read.status is None
    assert read.problem == "stale"

    bad = tmp_path / "bad.xml"
    snap = junit.snapshot_reports([good, bad, gone])
    _write_fresh(good, _case("a"), snap)
    _write_fresh(bad, "<testsuite>", snap)
    assert junit.read_reports(snap).problem == "invalid"


def test_folder_with_a_fresh_report_has_no_problem(tmp_path: Path) -> None:
    """Older reports left in a folder beside this run's report are not a problem."""
    folder = tmp_path / "reports"
    folder.mkdir()
    (folder / "TEST-old.xml").write_text(_case("old"))
    snap = junit.snapshot_reports([folder])
    _write_fresh(folder / "TEST-new.xml", _case("new"), snap)

    assert junit.read_reports(snap).problem is None


def test_status_priority_when_nothing_is_read(tmp_path: Path) -> None:
    """Invalid outranks stale, and stale outranks missing."""
    stale, bad, gone = tmp_path / "s.xml", tmp_path / "b.xml", tmp_path / "g.xml"
    stale.write_text(_case("a"))
    snap = junit.snapshot_reports([stale, bad, gone])
    assert junit.read_reports(snap).status == "stale"

    _write_fresh(bad, "<testsuite>", snap)
    assert junit.read_reports(snap).status == "invalid"


def test_read_collapses_attempts_across_reports(tmp_path: Path) -> None:
    """Attempts of one test across several reports merge into one result."""
    one, two = tmp_path / "1.xml", tmp_path / "2.xml"
    snap = junit.snapshot_reports([one, two])
    _write_fresh(one, '<testsuite><testcase name="t"><failure/></testcase></testsuite>', snap)
    _write_fresh(two, _case("t"), snap)

    assert junit.read_reports(snap).results == [("t", "retried", None)]


def test_write_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Results land in a private per-run file, capped at MAX_TESTS."""
    results: list[junit.TestResult] = [("a", "pass", 0.5), ("b", "fail", None), ("c", "skip", None)]

    assert junit.write_results("ev1", results, state=tmp_path) == (3, False)
    target = tmp_path / "tests" / "ev1.json"
    assert json.loads(target.read_text()) == [
        ["a", "pass", 0.5],
        ["b", "fail", None],
        ["c", "skip", None],
    ]
    assert target.stat().st_mode & 0o777 == 0o600
    assert [p.name for p in target.parent.iterdir()] == ["ev1.json"]

    monkeypatch.setattr(junit, "MAX_TESTS", 2)
    assert junit.write_results("ev2", results, state=tmp_path) == (2, True)
    assert len(json.loads((tmp_path / "tests" / "ev2.json").read_text())) == 2


def test_failed_write_leaves_no_temp_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failure while writing re-raises and leaves nothing behind."""

    def boom(*_args: object, **_kwargs: object) -> None:
        msg = "disk full"
        raise OSError(msg)

    monkeypatch.setattr(junit.json, "dump", boom)

    with pytest.raises(OSError, match="disk full"):
        junit.write_results("ev1", [("a", "pass", None)], state=tmp_path)

    assert list((tmp_path / "tests").iterdir()) == []


@pytest.mark.parametrize("event_id", ["", ".", "..", "a/b", "a\\b", "../x"])
def test_write_results_rejects_non_file_name_ids(tmp_path: Path, event_id: str) -> None:
    """An id that is not a plain file name is refused before anything is written."""
    with pytest.raises(ValueError, match="plain file name"):
        junit.write_results(event_id, [], state=tmp_path)

    assert not (tmp_path / "tests").exists()
