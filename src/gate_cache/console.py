"""User-facing gate-cache messages."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_DIM = "\033[2m"
_RESET = "\033[0m"
_MINUTE = 60
_HOUR = 3600


def say(message: str, *, end: str = "\n") -> None:
    """Print a gate-cache message to stderr, verbatim.

    Args:
        message: Text to print after the `gate-cache: ` prefix.
        end: Text printed after the message; empty for a prompt that waits on the same line.
    """
    print(f"gate-cache: {message}", end=end, file=sys.stderr, flush=True)  # noqa: T201


def stdin_isatty() -> bool:
    """Return whether standard input is a terminal, treating a missing stdin as not one."""
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (OSError, ValueError):
        return False


def confirm_deletion(action: str, warning: Sequence[str]) -> bool:
    """Warn that a deletion is permanent and return True only when the user types `yes`.

    Call before any command deletes data the user asked to delete. Without a terminal on
    stdin nobody can answer, so refuse rather than block or guess; the caller's `--yes`
    flag skips this call.

    Args:
        action: The command's verb phrase, such as `clear stats`, used in the prompt.
        warning: What is deleted and what is lost; the first line is the headline.

    Returns:
        True when the user typed `yes`, False when they refused or could not answer.
    """
    if not stdin_isatty():
        say(f"refusing to {action} without confirmation; pass --yes to {action} non-interactively")
        return False
    headline, *details = warning
    say(f"WARNING: {headline}")
    for line in [*details, "This cannot be undone."]:
        say(f"  {line}")
    say(f"type 'yes' to {action}: ", end="")
    try:
        answer = input()
    except (EOFError, KeyboardInterrupt) as interrupt:
        print(file=sys.stderr)  # noqa: T201
        say("aborted; nothing was deleted")
        if isinstance(interrupt, KeyboardInterrupt):
            raise
        return False
    if answer.strip() != "yes":
        say("aborted; nothing was deleted")
        return False
    return True


def _use_color() -> bool:
    """Return True when stdout is a terminal that accepts ANSI styling."""
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


def kv_text(rows: dict[str, str]) -> str:
    """Return key/value rows as text with the values aligned in one column.

    Use it to build a larger block of text; `kv` prints the same rows directly.

    Args:
        rows: Labels mapped to their values, in display order.

    Returns:
        str: One line per row and per extra value line, each ending in a newline.
    """
    if not rows:
        return ""
    cell_width = max(len(key) for key in rows) + len(": ")
    dim, reset = (_DIM, _RESET) if _use_color() else ("", "")
    lines: list[str] = []
    for key, value in rows.items():
        pad = " " * (cell_width - len(key) - len(": "))
        first, *rest = value.splitlines() or [""]
        lines.append(f"  {dim}{key}{reset}: {pad}{first}")
        lines.extend(f"{' ' * (2 + cell_width)}{line}" for line in rest)
    return "".join(f"{line}\n" for line in lines)


def kv(rows: dict[str, str]) -> None:
    """Print key/value rows on stdout with the values aligned in one column.

    Args:
        rows: Labels mapped to their values, printed in insertion order.
    """
    sys.stdout.write(kv_text(rows))


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
