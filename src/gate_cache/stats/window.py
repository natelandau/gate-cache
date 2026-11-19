"""Parse the time window of a stats report."""

from __future__ import annotations

import contextlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DURATION_ERROR = "--since takes a number and a unit h, d, w, or y, e.g. --since 7d"
UNTIL_ERROR = (
    "--until takes a date, a timestamp, or a duration, "
    "e.g. --until 2026-11-01, --until 2026-11-01T12:00:00Z, or --until 1d"
)

Bucket = Literal["day", "week", "month"]

_UNIT_SECONDS: dict[str, int] = {"h": 3600, "d": 86400, "w": 7 * 86400, "y": 365 * 86400}
_DURATION = re.compile(r"([1-9]\d*)([hdwy])")
_MAX_DAY_BUCKET_DAYS = 31
_MAX_WEEK_BUCKET_DAYS = 366
_LOCALTIME = Path("/etc/localtime")
_TIMEZONE_FILE = Path("/etc/timezone")


def parse_duration(text: str) -> float:
    """Convert a duration such as `7d` to seconds so a window can be set relative to now."""
    match = _DURATION.fullmatch(text)
    if match is None:
        raise ValueError(DURATION_ERROR)
    try:
        return float(int(match[1]) * _UNIT_SECONDS[match[2]])
    except (OverflowError, ValueError):
        raise ValueError(DURATION_ERROR) from None


def parse_until(text: str, *, now: float, tz: ZoneInfo) -> float:
    """Resolve the end of a window to Unix seconds, never later than `now`.

    Raises:
        ValueError: When the text is no date, timestamp, or duration, or falls before 1970,
            where no run can be recorded.
    """
    try:
        seconds = now - parse_duration(text)
    except ValueError:
        try:
            moment = datetime.fromisoformat(text)
            # A naive value and a bare date both mean the user's local time.
            seconds = (
                moment.replace(tzinfo=tz).timestamp()
                if moment.tzinfo is None
                else moment.timestamp()
            )
        except (OverflowError, ValueError, OSError):
            raise ValueError(UNTIL_ERROR) from None
    if seconds < 0:
        raise ValueError(UNTIL_ERROR)
    return min(seconds, now)


def parse_window(since: str, until: str | None, *, now: float, tz: ZoneInfo) -> tuple[float, float]:
    """Resolve `--since` and `--until` to the start and end of a window in Unix seconds.

    `since` is the window's length, counted back from its end. A start before 1970 moves
    to 1970, since no run is older and earlier dates cannot be printed.

    Raises:
        ValueError: When either value cannot be parsed.
    """
    length = parse_duration(since)
    end = now if until is None else parse_until(until, now=now, tz=tz)
    return max(end - length, 0.0), end


def bucket_for(days: float) -> Bucket:
    """Pick a chart bucket size that keeps the point count readable for a window of `days`."""
    if days <= _MAX_DAY_BUCKET_DAYS:
        return "day"
    if days <= _MAX_WEEK_BUCKET_DAYS:
        return "week"
    return "month"


def local_zone() -> ZoneInfo:
    """Return the machine's named time zone, so dates in a report fall on the user's local days.

    The standard library has no lookup of the local zone name: `TZ` wins, then the zone file
    that `/etc/localtime` links to, then the name in `/etc/timezone`, then UTC.
    """
    candidates: list[str] = []
    if tz := os.environ.get("TZ", "").removeprefix(":"):
        candidates.append(tz)
    try:
        parts = _LOCALTIME.resolve(strict=True).parts
    except OSError:
        parts = ()
    if "zoneinfo" in parts:
        start = len(parts) - parts[::-1].index("zoneinfo")
        candidates.append("/".join(parts[start:]))
    with contextlib.suppress(OSError, UnicodeDecodeError):
        candidates.append(_TIMEZONE_FILE.read_text(encoding="utf-8").strip())
    for name in candidates:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            continue
    return ZoneInfo("UTC")
