"""How often a run that would skip runs the command anyway."""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gate_cache.config import config_whole_number, parse_whole_number, valid_config_value
from gate_cache.console import say

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

SPOT_CHECK_ENV = "GATE_CACHE_SPOT_CHECK_ONE_RUN_IN"
CONFIG_KEY = "spot_check_one_run_in"
DEFAULT_ONE_RUN_IN = 50
_HINT = "use a whole number, 0 or more"


@dataclass(frozen=True)
class SpotCheck:
    """Whether a spot check is due, whether the flag forced it, and the rate that applied."""

    due: bool
    forced: bool
    one_run_in: int


def one_run_in(environ: Mapping[str, str] | None = None) -> int:
    """Resolve N, where a run that would skip runs anyway about 1 time in N.

    The environment variable beats the config file, which beats the default. An invalid
    value warns and falls through to the next source; it never fails a run.

    Args:
        environ: The environment to read. None reads the process environment.

    Returns:
        N. 0 turns spot checks off.
    """
    env = os.environ if environ is None else environ
    raw = env.get(SPOT_CHECK_ENV, "")
    if raw.strip():
        if (parsed := parse_whole_number(raw)) is not None:
            return parsed
        say(f"warning: ignoring invalid {SPOT_CHECK_ENV} {raw!r}; {_HINT}")
    configured = valid_config_value(CONFIG_KEY, parse=config_whole_number, hint=_HINT)
    return DEFAULT_ONE_RUN_IN if configured is None else configured


def decide(
    *,
    forced: bool,
    environ: Mapping[str, str] | None = None,
    chance: Callable[[], float] = random.random,
) -> SpotCheck:
    """Roll whether this run is a spot check.

    Args:
        forced: True when the `--spot-check` flag was given.
        environ: The environment to read the rate from. None reads the process environment.
        chance: Returns a number in [0, 1); injectable for tests.

    Returns:
        The decision. A forced run is always due and never reads the setting.
    """
    if forced:
        return SpotCheck(due=True, forced=True, one_run_in=0)
    n = one_run_in(environ)
    return SpotCheck(due=n > 0 and chance() < 1 / n, forced=False, one_run_in=n)
