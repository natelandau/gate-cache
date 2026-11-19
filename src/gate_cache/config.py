"""Where the user config file lives and how to read one key of it."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, TypeVar

from platformdirs import user_config_path

from gate_cache.console import say

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_APP = "gate-cache"
_T = TypeVar("_T")
# Far beyond any real setting, and small enough to add to a float clock without overflow.
MAX_WHOLE_NUMBER = 10**15


def config_path() -> Path:
    """Return the path of the user config file."""
    return user_config_path(_APP, appauthor=False) / "config.toml"


_data_cache: tuple[tuple[Path, int, int], dict[str, object]] | None = None


def config_value(key: str) -> object | None:
    """Return one top-level value of the config file, or None when it is unusable.

    Args:
        key: The key name, such as `stats_enabled` or `wait_timeout`.

    Returns:
        The value, or None when the file or key is missing or the file is invalid.
    """
    global _data_cache  # noqa: PLW0603
    path = config_path()
    try:
        info = path.stat()
    except OSError:
        return None
    # A recorded gate run looks keys up several times; re-parse only when the file
    # changes, so a long-running dashboard still sees edits.
    stamp = (path, info.st_mtime_ns, info.st_size)
    if _data_cache is not None and _data_cache[0] == stamp:
        data = _data_cache[1]
    else:
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            return None
        _data_cache = (stamp, data)
    return data.get(key)


def parse_whole_number(text: str) -> int | None:
    """Parse a non-negative whole number, or return None when the text is not one.

    Args:
        text: The value to parse; padded spaces are allowed.

    Returns:
        The number, capped at MAX_WHOLE_NUMBER, or None.
    """
    stripped = text.strip()
    if not (stripped.isascii() and stripped.isdigit()):
        return None
    # int() refuses strings past a few thousand digits, so cap by length first.
    digits = stripped.lstrip("0") or "0"
    if len(digits) > len(str(MAX_WHOLE_NUMBER)):
        return MAX_WHOLE_NUMBER
    return min(int(digits), MAX_WHOLE_NUMBER)


def config_whole_number(value: object) -> int | None:
    """Return a config value as a capped non-negative integer, or None when it is not one."""
    # bool is an int subclass, so reject it first.
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return min(value, MAX_WHOLE_NUMBER)
    return None


def valid_config_value(key: str, *, parse: Callable[[object], _T | None], hint: str) -> _T | None:
    """Read one key, warning and returning None when it is set but invalid.

    Args:
        key: The key name.
        parse: Turns the raw value into the setting, or None when it is invalid.
        hint: What a valid value looks like, for the warning.

    Returns:
        The parsed value, or None when the key is unset or invalid.
    """
    value = config_value(key)
    if value is None:
        return None
    if (parsed := parse(value)) is not None:
        return parsed
    say(f"warning: ignoring invalid {key} {value!r} in the config file; {hint}")
    return None
