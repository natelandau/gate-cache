"""Read on/off environment variables."""

from __future__ import annotations

CI_ENV = "CI"


def flag_on(value: str) -> bool:
    """Read an on/off variable the way CI systems set CI, so `false` means off.

    Args:
        value: The variable's value.

    Returns:
        False for empty, `0`, and `false` in any case, True otherwise.
    """
    return value.strip().lower() not in {"", "0", "false"}
