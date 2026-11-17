"""Where the user config file lives and how to read one table of it."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

from platformdirs import user_config_path

if TYPE_CHECKING:
    from pathlib import Path

_APP = "gate-cache"


def config_path() -> Path:
    """Return the path of the user config file."""
    return user_config_path(_APP, appauthor=False) / "config.toml"


_data_cache: tuple[tuple[Path, int, int], dict[str, object]] | None = None


def config_table(name: str) -> dict[str, object]:
    """Return one table of the config file, or an empty one when the file is unusable.

    Args:
        name: The table name, such as `stats` or `wait`.

    Returns:
        The table's keys, or an empty dict when the file or table is missing or invalid.
    """
    global _data_cache  # noqa: PLW0603
    path = config_path()
    try:
        info = path.stat()
    except OSError:
        return {}
    # A recorded gate run looks the table up several times; re-parse only when the file
    # changes, so a long-running dashboard still sees edits.
    key = (path, info.st_mtime_ns, info.st_size)
    if _data_cache is not None and _data_cache[0] == key:
        data = _data_cache[1]
    else:
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            return {}
        _data_cache = (key, data)
    table = data.get(name)
    return table if isinstance(table, dict) else {}
