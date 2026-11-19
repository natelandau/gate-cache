"""How gate names group, shared by the markers and the stats without loading sqlite3."""

from __future__ import annotations

# A name that holds one of these is a command line, never a gate plus an `@` key.
GATE_WHITESPACE = " \t\n\v\f\r"


def gate_of(name: str) -> str:
    """Return the gate a name counts toward, so `test@v22` and `test@v20` group as `test`.

    The stats archive applies the same rule in SQL as `GATE_EXPRESSION`.

    Args:
        name: A gate name, with or without an `@` key.

    Returns:
        str: The part before the first `@`, or the whole name when it has no key.
    """
    at = name.find("@")
    if 0 < at < len(name) - 1 and not any(c in GATE_WHITESPACE for c in name):
        return name[:at]
    return name
