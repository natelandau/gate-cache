"""Tests for the store of each gate's recent run times."""

import json
from pathlib import Path

import pytest

from gate_cache.durations import DURATIONS_DIRNAME, durations_path, record_duration, usual_duration


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("[2]", 2.0),
        ("[1, 3]", 2.0),
        ("[5, 1, 3]", 3.0),
        ("[1, 2, 3, 4, 100]", 3.0),
        ("[1000, 1000, 1, 2, 3, 4, 5]", 3.0),
        ('[2, -1, "x", true, 1e300, 4]', 3.0),
    ],
)
def test_usual_duration_median(tmp_path: Path, content: str, expected: float) -> None:
    """Verify the estimate is the median of the last five valid run times."""
    path = tmp_path / "d.json"
    path.write_text(content, encoding="utf-8")

    assert usual_duration(path) == expected


@pytest.mark.parametrize("content", [None, "", "not json", "{}", "[]", '["x", -1]', "[NaN]"])
def test_usual_duration_unusable(tmp_path: Path, content: str | None) -> None:
    """Verify a missing, corrupt, or empty store gives no estimate."""
    path = tmp_path / "d.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")

    assert usual_duration(path) is None


def test_record_duration_keeps_last_five(tmp_path: Path) -> None:
    """Verify recording keeps only the five newest run times, oldest first."""
    path = durations_path(tmp_path, "pytest")

    for seconds in range(1, 8):
        record_duration(path, float(seconds))

    assert json.loads(path.read_text(encoding="utf-8")) == [3, 4, 5, 6, 7]


def test_record_duration_replaces_corrupt_file(tmp_path: Path) -> None:
    """Verify recording over a corrupt store starts a fresh list."""
    path = durations_path(tmp_path, "pytest")
    path.parent.mkdir()
    path.write_text("not json", encoding="utf-8")

    record_duration(path, 2.5)

    assert usual_duration(path) == 2.5


def test_record_duration_unwritable_is_silent(tmp_path: Path) -> None:
    """Verify a store that cannot be written does not raise."""
    (tmp_path / DURATIONS_DIRNAME).write_text("a file, not a directory", encoding="utf-8")

    record_duration(durations_path(tmp_path, "pytest"), 1.0)
