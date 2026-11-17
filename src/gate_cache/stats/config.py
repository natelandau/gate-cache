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

from platformdirs import user_config_path, user_state_path

from gate_cache.env import CI_ENV, flag_on

if TYPE_CHECKING:
    from collections.abc import Mapping

STATS_ENV = "GATE_CACHE_STATS"
_APP = "gate-cache"
_TABLE = "[stats]"
_STATS_HEADER = re.compile(r"^\s*\[\s*stats\s*\]\s*(#.*)?$")
_ENABLED_KEY = re.compile(r"^\s*enabled\s*=")
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


def config_path() -> Path:
    """Return the path of the user config file."""
    return user_config_path(_APP, appauthor=False) / "config.toml"


def state_dir() -> Path:
    """Return the directory that holds stats data."""
    return user_state_path(_APP, appauthor=False)


def _config_value() -> bool | None:
    """Return `[stats] enabled` from the config file, or None when absent or invalid."""
    try:
        data = tomllib.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    table = data.get("stats")
    value = table.get("enabled") if isinstance(table, dict) else None
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
    """Return config text with `[stats] enabled` set, keeping every other line."""
    line = f"enabled = {'true' if enabled else 'false'}"
    lines = text.splitlines()
    insert_at: int | None = None
    in_stats = False
    for index, current in enumerate(lines):
        if current.lstrip().startswith("["):
            in_stats = _STATS_HEADER.match(current) is not None
            if in_stats:
                insert_at = index + 1
        elif in_stats and _ENABLED_KEY.match(current):
            lines[index] = line
            return "\n".join(lines) + "\n"
    if insert_at is not None:
        lines.insert(insert_at, line)
        return "\n".join(lines) + "\n"
    prefix = "\n".join(lines) + "\n\n" if lines else ""
    return f"{prefix}{_TABLE}\n{line}\n"


def _updated_text(text: str, *, enabled: bool) -> str:
    """Return the new config text, refusing input it cannot edit safely."""
    if text.strip():
        try:
            tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            msg = f"the file is not valid TOML ({error}); fix it first"
            raise ConfigError(msg) from error
    updated = _with_enabled(text, enabled=enabled)
    try:
        stats = tomllib.loads(updated).get("stats")
    except tomllib.TOMLDecodeError:
        stats = None
    if not isinstance(stats, dict) or stats.get("enabled") is not enabled:
        msg = "could not set [stats] enabled safely; set it by hand in a [stats] table"
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
    path = config_path().resolve()
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
