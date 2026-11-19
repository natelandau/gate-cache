"""How long a run waits for a run in progress, and what it does when that run failed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gate_cache.config import (
    config_whole_number,
    valid_config_value,
)

DEFAULT_WAIT_TIMEOUT = 900
FailedBehavior = Literal["rerun", "report"]
_FAILED_BEHAVIORS: dict[str, FailedBehavior] = {"rerun": "rerun", "report": "report"}


@dataclass(frozen=True)
class WaitSettings:
    """The wait limit in seconds and the behavior when the awaited run failed."""

    timeout: int = DEFAULT_WAIT_TIMEOUT
    failed: FailedBehavior = "rerun"


def parse_failed(text: str) -> FailedBehavior | None:
    """Parse a failure behavior, or return None when it is not `rerun` or `report`.

    Args:
        text: The value to parse.

    Returns:
        The behavior, or None when the text names neither.
    """
    return _FAILED_BEHAVIORS.get(text.strip())


def _config_failed(value: object) -> FailedBehavior | None:
    return parse_failed(value) if isinstance(value, str) else None


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
    if timeout is None:
        timeout = valid_config_value(
            "wait_timeout", parse=config_whole_number, hint="use whole seconds, 0 or more"
        )
    if failed is None:
        failed = valid_config_value(
            "wait_on_failure", parse=_config_failed, hint="use rerun or report"
        )
    return WaitSettings(
        timeout=DEFAULT_WAIT_TIMEOUT if timeout is None else timeout,
        failed="rerun" if failed is None else failed,
    )
