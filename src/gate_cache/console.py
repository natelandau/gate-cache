"""User-facing gate-cache messages."""

from __future__ import annotations

import re
import sys

_MINUTE = 60
_HOUR = 3600
# C0 and C1 control characters and DEL, except tab and newline.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
CONTROL_STAND_IN = "\N{REPLACEMENT CHARACTER}"


def printable(text: str) -> str:
    """Replace control characters, so names read from disk cannot drive the terminal.

    Gate, test, and branch names and holder paths come from files anyone with write access to
    the repository or stats folder can edit, and an escape sequence in one would run in the
    terminal that prints it.

    Args:
        text: Text about to be printed.

    Returns:
        The text with each control character other than tab and newline replaced.
    """
    return _CONTROL.sub(CONTROL_STAND_IN, text)


def say(message: str, *, end: str = "\n") -> None:
    """Print a gate-cache message to stderr, verbatim.

    Args:
        message: Text to print after the `gate-cache: ` prefix.
        end: Text printed after the message; empty for a prompt that waits on the same line.
    """
    print(f"gate-cache: {printable(message)}", end=end, file=sys.stderr, flush=True)  # noqa: T201


def stdin_isatty() -> bool:
    """Return whether standard input is a terminal, treating a missing stdin as not one."""
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (OSError, ValueError):
        return False


def plural(count: float, noun: str) -> str:
    """Return a count with its noun, adding an `s` unless the count is exactly one.

    Args:
        count: How many there are.
        noun: The singular noun, such as `run`.
    """
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


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
