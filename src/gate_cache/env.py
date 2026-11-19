"""Read on/off environment variables and adjust the environment the wrapped command sees."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

CI_ENV = "CI"


def flag_on(value: str) -> bool:
    """Read an on/off variable the way CI systems set CI, so `false` means off.

    Args:
        value: The variable's value.

    Returns:
        False for empty, `0`, and `false` in any case, True otherwise.
    """
    return value.strip().lower() not in {"", "0", "false"}


def _same_path(entry: str, target: Path) -> bool:
    # An empty PATH entry means the current directory, never the hook environment.
    if not entry:
        return False
    try:
        return Path(entry).resolve() == target
    except RuntimeError:
        # Path.resolve raises on a symlink loop before Python 3.13; a loop is never the hook env.
        return False


def hook_environment(environ: Mapping[str, str], prefix: str) -> dict[str, str]:
    """Return environ with gate-cache's own virtual environment moved out of the command's way.

    prek and pre-commit run a Python hook with its virtual environment first on PATH and in
    VIRTUAL_ENV, so a bare tool name in the hook's args would find the hook's copy or
    nothing. Moving that bin/ to the end, instead of removing it, keeps tools installed into
    the hook with additional_dependencies as a fallback.

    Args:
        environ: The environment gate-cache was started with.
        prefix: The root of the virtual environment gate-cache runs from.

    Returns:
        A copy of environ with the user's PATH first and the hook's VIRTUAL_ENV removed.
    """
    root = Path(prefix).resolve()
    hook_bin = root / "bin"
    result = dict(environ)
    if "PATH" in result:
        entries = result["PATH"].split(os.pathsep)
        # A stable sort keeps the order within the user's entries and within the hook's.
        entries.sort(key=lambda entry: _same_path(entry=entry, target=hook_bin))
        result["PATH"] = os.pathsep.join(entries)
    if _same_path(entry=result.get("VIRTUAL_ENV", ""), target=root):
        del result["VIRTUAL_ENV"]
    return result
