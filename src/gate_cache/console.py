"""User-facing gate-cache messages."""

from __future__ import annotations

from nclutils import pp


def say(message: str) -> None:
    """Print a gate-cache message to stderr, verbatim.

    Args:
        message: Text to print after the `gate-cache: ` prefix.
    """
    pp.err_console().print(f"gate-cache: {message}", markup=False, highlight=False, soft_wrap=True)
