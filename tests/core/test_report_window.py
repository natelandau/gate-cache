"""Tests for the report time-window parsing."""

import re
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from gate_cache.stats.window import (
    DURATION_ERROR,
    UNTIL_ERROR,
    bucket_for,
    local_zone,
    parse_duration,
    parse_until,
    parse_window,
)

NOW: float = datetime(2026, 11, 18, 12, 0, tzinfo=UTC).timestamp()
NEW_YORK = ZoneInfo("America/New_York")


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("12h", 43200), ("7d", 604800), ("2w", 1209600), ("1y", 31536000)],
)
def test_parse_duration(text: str, seconds: int) -> None:
    """Convert each unit to seconds."""
    assert parse_duration(text) == seconds


@pytest.mark.parametrize(
    "text", ["", "7", "d", "0d", "-1d", "1.5d", "7m", "7 d", "9" * 400 + "d", "9" * 5000 + "d"]
)
def test_parse_duration_rejects(text: str) -> None:
    """Reject text that is not a whole number plus a unit."""
    with pytest.raises(ValueError, match=re.escape(DURATION_ERROR)):
        parse_duration(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-11-01", datetime(2026, 11, 1, tzinfo=NEW_YORK).timestamp()),
        ("2026-11-01T09:30:00", datetime(2026, 11, 1, 9, 30, tzinfo=NEW_YORK).timestamp()),
        ("2026-11-01T12:00:00Z", datetime(2026, 11, 1, 12, tzinfo=UTC).timestamp()),
        ("7d", NOW - 7 * 86400),
        ("2099-01-01", NOW),
    ],
)
def test_parse_until(text: str, expected: float) -> None:
    """Resolve dates, timestamps, and durations, clamped to now."""
    assert parse_until(text, now=NOW, tz=NEW_YORK) == expected


@pytest.mark.parametrize(
    "text", ["", "yesterday", "2026-13-45", "0d", "0001-01-01", "1969-12-31", "10000y"]
)
def test_parse_until_rejects(text: str) -> None:
    """Reject text that is no date, timestamp, or duration."""
    with pytest.raises(ValueError, match=re.escape(UNTIL_ERROR)):
        parse_until(text, now=NOW, tz=NEW_YORK)


@pytest.mark.parametrize(
    ("since", "until", "expected"),
    [
        pytest.param("7d", None, (NOW - 7 * 86400, NOW), id="ends now"),
        pytest.param("7d", "7d", (NOW - 14 * 86400, NOW - 7 * 86400), id="length back from until"),
        pytest.param("10000y", None, (0.0, NOW), id="start before 1970"),
    ],
)
def test_parse_window(since: str, until: str | None, expected: tuple[float, float]) -> None:
    """--since is the length counted back from --until, and the start never precedes 1970."""
    assert parse_window(since, until, now=NOW, tz=NEW_YORK) == expected


@pytest.mark.parametrize(
    ("days", "bucket"),
    [(1, "day"), (31, "day"), (32, "week"), (366, "week"), (367, "month")],
)
def test_bucket_for(days: float, bucket: str) -> None:
    """Choose coarser buckets for longer windows."""
    assert bucket_for(days) == bucket


@pytest.mark.parametrize(
    ("tz", "expected"),
    [(":Europe/Paris", "Europe/Paris"), ("Asia/Tokyo", "Asia/Tokyo")],
)
def test_local_zone_follows_tz(monkeypatch: pytest.MonkeyPatch, tz: str, expected: str) -> None:
    """TZ, with or without its leading colon, names the local zone."""
    monkeypatch.setenv("TZ", tz)
    assert local_zone().key == expected


@pytest.mark.parametrize(
    ("timezone_file", "expected"),
    [("Europe/Berlin\n", "Europe/Berlin"), (None, "UTC"), ("Not/AZone\n", "UTC")],
)
def test_local_zone_without_tz_or_link(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, timezone_file: str | None, expected: str
) -> None:
    """With no usable TZ and no zone file link, /etc/timezone names the zone, else UTC."""
    monkeypatch.setenv("TZ", "Not/AZone")
    monkeypatch.setattr("gate_cache.stats.window._LOCALTIME", tmp_path / "missing")
    names = tmp_path / "timezone"
    if timezone_file is not None:
        names.write_text(timezone_file, encoding="utf-8")
    monkeypatch.setattr("gate_cache.stats.window._TIMEZONE_FILE", names)
    assert local_zone().key == expected
