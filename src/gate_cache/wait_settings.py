"""How long a run waits for a run in progress, and what it does when that run failed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeVar

from gate_cache.config import config_table
from gate_cache.console import say

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULT_WAIT_TIMEOUT = 900
# Far beyond any real wait, and small enough to add to a float clock without overflow.
MAX_WAIT_TIMEOUT = 10**15
FailedBehavior = Literal["rerun", "report"]
_FAILED_BEHAVIORS: dict[str, FailedBehavior] = {"rerun": "rerun", "report": "report"}
_T = TypeVar("_T")


@dataclass(frozen=True)
class WaitSettings:
    """The wait limit in seconds and the behavior when the awaited run failed."""

    timeout: int = DEFAULT_WAIT_TIMEOUT
    failed: FailedBehavior = "rerun"


def parse_timeout(text: str) -> int | None:
    """Parse a whole number of seconds, or return None when it is not one.

    Args:
        text: The value to parse.

    Returns:
        The seconds, capped at MAX_WAIT_TIMEOUT, or None when the text is not a
        non-negative integer.
    """
    stripped = text.strip()
    if not (stripped.isascii() and stripped.isdigit()):
        return None
    # int() refuses strings past a few thousand digits, so cap by length first.
    digits = stripped.lstrip("0") or "0"
    if len(digits) > len(str(MAX_WAIT_TIMEOUT)):
        return MAX_WAIT_TIMEOUT
    return min(int(digits), MAX_WAIT_TIMEOUT)


def parse_failed(text: str) -> FailedBehavior | None:
    """Parse a failure behavior, or return None when it is not `rerun` or `report`.

    Args:
        text: The value to parse.

    Returns:
        The behavior, or None when the text names neither.
    """
    return _FAILED_BEHAVIORS.get(text.strip())


def _config_timeout(value: object) -> int | None:
    # bool is an int subclass, so reject it first.
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return min(value, MAX_WAIT_TIMEOUT)
    return None


def _config_failed(value: object) -> FailedBehavior | None:
    return parse_failed(value) if isinstance(value, str) else None


def _config_value(
    table: dict[str, object], key: str, *, parse: Callable[[object], _T | None], hint: str
) -> _T | None:
    """Read one `[wait]` value, warning and returning None when it is set but invalid."""
    value = table.get(key)
    if value is None:
        return None
    if (parsed := parse(value)) is not None:
        return parsed
    say(f"warning: ignoring invalid [wait] {key} {value!r}; {hint}")
    return None


def wait_settings(
    *, timeout: int | None = None, failed: FailedBehavior | None = None
) -> WaitSettings:
    """Resolve the wait settings from flags, then the config file, then defaults.

    An invalid config value warns and falls back to the default; it never fails a run.

    Args:
        timeout: The `--wait-timeout` flag value, if given.
        failed: The `--on-wait-failure` flag value, if given.

    Returns:
        The settings to use.
    """
    table = config_table("wait") if timeout is None or failed is None else {}
    if timeout is None:
        timeout = _config_value(
            table, "timeout", parse=_config_timeout, hint="use whole seconds, 0 or more"
        )
    if failed is None:
        failed = _config_value(table, "failed", parse=_config_failed, hint="use rerun or report")
    return WaitSettings(
        timeout=DEFAULT_WAIT_TIMEOUT if timeout is None else timeout,
        failed="rerun" if failed is None else failed,
    )
