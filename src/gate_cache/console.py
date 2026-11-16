"""User-facing gate-cache messages."""

from __future__ import annotations

import os
import sys

_DIM = "\033[2m"
_RESET = "\033[0m"
_MINUTE = 60
_HOUR = 3600


def say(message: str) -> None:
    """Print a gate-cache message to stderr, verbatim.

    Args:
        message: Text to print after the `gate-cache: ` prefix.
    """
    print(f"gate-cache: {message}", file=sys.stderr)  # noqa: T201


def _use_color() -> bool:
    """Return True when stdout is a terminal that accepts ANSI styling."""
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


def kv(rows: dict[str, str]) -> None:
    """Print key/value rows on stdout with the values aligned in one column.

    Args:
        rows: Labels mapped to their values, printed in insertion order.
    """
    if not rows:
        return
    cell_width = max(len(key) for key in rows) + len(": ")
    dim, reset = (_DIM, _RESET) if _use_color() else ("", "")
    for key, value in rows.items():
        pad = " " * (cell_width - len(key) - len(": "))
        first, *rest = value.splitlines() or [""]
        print(f"  {dim}{key}{reset}: {pad}{first}")  # noqa: T201
        for line in rest:
            print(f"{' ' * (2 + cell_width)}{line}")  # noqa: T201


def format_duration(seconds: float) -> str:
    """Render a run time compactly for the skip line and status.

    Args:
        seconds: Elapsed time in seconds.

    Returns:
        `<1s` below one second, else `42s`, `1m 34s`, or `1h 2m`.
    """
    if seconds < 1:
        return "<1s"
    # Round half up; round() would round half to even.
    total = int(seconds + 0.5)
    if total < _MINUTE:
        return f"{total}s"
    if total < _HOUR:
        return f"{total // _MINUTE}m {total % _MINUTE}s"
    minutes = (total + _MINUTE // 2) // _MINUTE
    return f"{minutes // _MINUTE}h {minutes % _MINUTE}m"
