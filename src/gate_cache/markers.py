"""Marker files that record a gate command passing on a git tree."""

from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from nclutils.utils import iso_timestamp

if TYPE_CHECKING:
    from collections.abc import Sequence

MARKER_DIRNAME = "gate-cache"
TEMP_PREFIX = ".tmp-"


def marker_key(tree: str, name: str) -> str:
    """Compute the marker key for a tree and gate name.

    The key is the lowercase hex sha256 of tree, a NUL byte, and name. This is a public
    contract shared with shell consumers; changing it is a breaking change.

    Args:
        tree: Git tree hash.
        name: Gate name.

    Returns:
        The lowercase hex digest.
    """
    return hashlib.sha256(f"{tree}\0{name}".encode()).hexdigest()


def marker_dir(common_dir: Path) -> Path:
    """Return the marker directory inside a git common dir.

    Args:
        common_dir: Absolute path to the git common directory.

    Returns:
        The directory that holds markers.
    """
    return common_dir / MARKER_DIRNAME


def marker_path(common_dir: Path, tree: str, name: str) -> Path:
    """Return the marker file path for a tree and gate name.

    Args:
        common_dir: Absolute path to the git common directory.
        tree: Git tree hash.
        name: Gate name.

    Returns:
        The path whose existence signals a cached pass.
    """
    return marker_dir(common_dir) / marker_key(tree, name)


def write_marker(path: Path, *, tree: str, name: str, command: Sequence[str]) -> None:
    """Atomically write a marker file.

    Args:
        path: Destination marker path; its parent directory is created if needed.
        tree: Git tree hash the command passed on.
        name: Gate name.
        command: The command that passed.

    Raises:
        OSError: If the marker cannot be written. Any temp file is removed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tree": tree,
        "name": name,
        "command": list(command),
        "timestamp": iso_timestamp(),
    }
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=TEMP_PREFIX, delete=False
        ) as tmp:
            tmp_name = tmp.name
            json.dump(payload, tmp)
        Path(tmp_name).replace(path)
    except OSError:
        if tmp_name is not None:
            with contextlib.suppress(OSError):
                Path(tmp_name).unlink()
        raise


def passed_names(common_dir: Path, tree: str) -> list[str]:
    """List the gates with a recorded pass on a tree, for reporting what would skip.

    Marker filenames are one-way hashes, so names come from each marker's JSON content.
    A file whose content is missing, unreadable, or does not hash to its own filename is
    left out. Markers written by other tools without that content still count for skips
    but cannot be listed.

    Args:
        common_dir: Absolute path to the git common directory.
        tree: Git tree hash to match.

    Returns:
        Sorted, unique gate names.
    """
    names: set[str] = set()
    try:
        entries = list(marker_dir(common_dir).iterdir())
    except OSError:
        return []
    for entry in entries:
        if entry.name.startswith(TEMP_PREFIX):
            continue
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        name = data.get("name")
        if (
            data.get("tree") == tree
            and isinstance(name, str)
            and marker_key(tree, name) == entry.name
        ):
            names.add(name)
    return sorted(names)


def prune_markers(directory: Path, *, max_age_days: int = 30, now: float | None = None) -> None:
    """Delete markers older than the cutoff, ignoring every filesystem error.

    Args:
        directory: Marker directory to prune.
        max_age_days: Age in days beyond which a file is deleted.
        now: Current epoch time; defaults to the system clock.
    """
    cutoff = (time.time() if now is None else now) - max_age_days * 86400
    try:
        for entry in directory.iterdir():
            with contextlib.suppress(OSError):
                if entry.is_file() and not entry.is_symlink() and entry.stat().st_mtime < cutoff:
                    entry.unlink()
    except OSError:
        return


def clear_markers(common_dir: Path) -> int:
    """Delete every marker and the marker directory.

    Files that vanish mid-clear and leftover subdirectories are tolerated, so a concurrent
    writer cannot make clearing fail.

    Args:
        common_dir: Absolute path to the git common directory.

    Returns:
        The number of markers deleted, not counting in-flight temp files; 0 when the
        directory is missing.

    Raises:
        OSError: If the marker directory cannot be listed, a file cannot be deleted, or the
            directory remains afterward.
    """
    directory = marker_dir(common_dir)
    if not directory.is_dir():
        return 0
    count = 0
    for entry in directory.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            continue
        try:
            entry.unlink()
        except FileNotFoundError:
            continue
        if not entry.name.startswith(TEMP_PREFIX):
            count += 1
    try:
        directory.rmdir()
    except OSError:
        shutil.rmtree(directory, ignore_errors=True)
    if directory.exists():
        msg = f"could not remove {directory}"
        raise OSError(msg)
    return count
