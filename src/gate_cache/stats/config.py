"""The opt-in stats setting and where its config and data live."""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from platformdirs import user_state_path

from gate_cache import config as core_config
from gate_cache.env import CI_ENV, flag_on
from gate_cache.spot_check import DEFAULT_ONE_RUN_IN
from gate_cache.wait_settings import DEFAULT_WAIT_TIMEOUT

if TYPE_CHECKING:
    from collections.abc import Mapping

STATS_ENV = "GATE_CACHE_STATS"
DATA_DIR_ENV = "GATE_CACHE_DATA_DIR"
_APP = "gate-cache"
_ENABLED_KEY = re.compile(r"^\s*stats_enabled\s*=")
# A header ends in `]`, so a row of a multi-line array such as `[1, 2],` is not one.
_TABLE_HEADER = re.compile(r"^\s*\[.*\]\s*(#.*)?$")
_NEW_FILE_MODE = 0o644
# The stats data holds paths and host names, so only the user may read it.
STATE_DIR_MODE = 0o700
DASHBOARD_PORT = 7878


class ConfigError(Exception):
    """The config file exists but cannot be edited safely."""


@dataclass(frozen=True)
class StatsSetting:
    """Whether stats recording is on, and what decided it."""

    enabled: bool
    source: Literal["env", "ci", "config", "default"]


def state_dir(environ: Mapping[str, str] | None = None) -> Path:
    """Return the directory that holds stats data.

    GATE_CACHE_DATA_DIR, when not empty, decides, and a relative value resolves against
    the current directory. Otherwise `stats_data_dir` in the config file decides, and a
    relative value resolves against the config file's directory so every repository sees
    the same data. Otherwise the data lives in the platform state directory. A leading
    `~` expands in both.

    Args:
        environ: Environment to read; defaults to the process environment.

    Returns:
        The absolute path of the stats data directory.
    """
    env = os.environ if environ is None else environ
    if value := env.get(DATA_DIR_ENV, "").strip():
        # absolute() reads the cwd only for a relative path, so an absolute value still
        # works from a deleted directory.
        return _expand_user(value).absolute()
    configured = core_config.config_value("stats_data_dir")
    if isinstance(configured, str) and configured.strip():
        return core_config.config_path().parent / _expand_user(configured.strip())
    return user_state_path(_APP, appauthor=False)


def _expand_user(value: str) -> Path:
    """Expand a leading `~`, keeping the value as written when no home can be found.

    A shell leaves `~unknown-user` as written too, so an unresolvable value never stops
    the stats commands with a traceback.
    """
    path = Path(value)
    try:
        return path.expanduser()
    except RuntimeError:
        return path


def _config_value() -> bool | None:
    """Return `stats_enabled` from the config file, or None when absent or invalid."""
    value = core_config.config_value("stats_enabled")
    return value if isinstance(value, bool) else None


def stats_setting(environ: Mapping[str, str] | None = None) -> StatsSetting:
    """Decide whether stats recording is on.

    GATE_CACHE_STATS, when not empty, decides. Otherwise CI turns recording off, because a
    CI runner is not a developer's machine. Otherwise the config file decides, and
    recording defaults to off.

    Args:
        environ: Environment to read; defaults to the process environment.

    Returns:
        The setting and the source that decided it.
    """
    env = os.environ if environ is None else environ
    if value := env.get(STATS_ENV, "").strip():
        return StatsSetting(enabled=flag_on(value), source="env")
    if flag_on(env.get(CI_ENV, "")):
        return StatsSetting(enabled=False, source="ci")
    configured = _config_value()
    if configured is not None:
        return StatsSetting(enabled=configured, source="config")
    return StatsSetting(enabled=False, source="default")


def _with_enabled(text: str, *, enabled: bool) -> str:
    """Return config text with `stats_enabled` set, keeping every other line."""
    line = f"stats_enabled = {'true' if enabled else 'false'}"
    lines = text.splitlines()
    for index, current in enumerate(lines):
        # A top-level key can only appear before the first table header.
        if _TABLE_HEADER.match(current):
            break
        if _ENABLED_KEY.match(current):
            lines[index] = line
            return "\n".join(lines) + "\n"
    return "\n".join([line, *lines]) + "\n"


def config_template(*, enabled: bool) -> str:
    """Return the commented config file written when none exists.

    Only `stats_enabled` is active; every other setting is commented out at its default.
    """
    return f"""\
# gate-cache settings. Environment variables override these values.
# https://natelandau.github.io/gate-cache/reference/configuration/

# Record run stats for the dashboard. `gate-cache stats on` and `stats off` set this.
stats_enabled = {"true" if enabled else "false"}

# The directory for recorded stats. A relative path starts from this file's directory.
# stats_data_dir = "~/gate-cache-stats"

# The longest wait, in whole seconds, for another run of the same gate. 0 never waits.
# wait_timeout = {DEFAULT_WAIT_TIMEOUT}

# What to do when the run this run waited for failed: "rerun" runs the command,
# "report" exits with that failure.
# wait_on_failure = "rerun"

# Run about 1 in N runs that would skip, to check that the skip is still right. 0 turns this off.
# spot_check_one_run_in = {DEFAULT_ONE_RUN_IN}
"""


def _updated_text(text: str, *, enabled: bool) -> str:
    """Return the new config text, refusing input it cannot edit safely."""
    if text.strip():
        try:
            tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            msg = f"the file is not valid TOML ({error}); fix it first"
            raise ConfigError(msg) from error
    updated = (
        _with_enabled(text, enabled=enabled) if text.strip() else config_template(enabled=enabled)
    )
    try:
        value = tomllib.loads(updated).get("stats_enabled")
    except tomllib.TOMLDecodeError:
        value = None
    if value is not enabled:
        msg = "could not set stats_enabled safely; set it by hand at the top of the file"
        raise ConfigError(msg)
    return updated


def write_enabled(*, enabled: bool) -> None:
    """Persist the stats setting in the config file, keeping the rest of the file.

    The file is replaced atomically. A symlinked file is updated through the link, and an
    existing file keeps its permissions.

    Args:
        enabled: Whether recording should be on.

    Raises:
        ConfigError: When the existing file cannot be edited safely.
        OSError: When the file cannot be read or written.
    """
    path = core_config.config_path().resolve()
    try:
        text = path.read_text(encoding="utf-8")
        mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        text, mode = "", _NEW_FILE_MODE
    except UnicodeDecodeError as error:
        msg = "the file is not valid UTF-8; fix it first"
        raise ConfigError(msg) from error
    updated = _updated_text(text, enabled=enabled)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=".config-", suffix=".tmp", delete=False
        ) as handle:
            temp = Path(handle.name)
            handle.write(updated)
        temp.chmod(mode)
        temp.replace(path)
    except BaseException:
        if temp is not None:
            with contextlib.suppress(OSError):
                temp.unlink()
        raise
