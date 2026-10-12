"""Marker files that record a gate command passing on a git tree."""

from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

MARKER_DIRNAME = "gate-cache"
TEMP_PREFIX = ".tmp-"
MISS_SUFFIX = ".miss"


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


def miss_path(common_dir: Path, tree: str, name: str) -> Path:
    """Return the path that records a gate run on a tree that did not pass.

    The suffix keeps it apart from the marker, whose existence alone signals a pass.

    Args:
        common_dir: Absolute path to the git common directory.
        tree: Git tree hash.
        name: Gate name.

    Returns:
        The miss record path.
    """
    return marker_dir(common_dir) / f"{marker_key(tree, name)}{MISS_SUFFIX}"


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
    _write_json(path, {"tree": tree, "name": name, "command": list(command)})


def write_miss(
    path: Path, *, tree: str, name: str, command: Sequence[str], exit_code: int, reason: str
) -> None:
    """Atomically record that a gate ran on a tree and did not pass.

    Args:
        path: Destination miss record path; its parent directory is created if needed.
        tree: Git tree hash the command ran on.
        name: Gate name.
        command: The command that ran.
        exit_code: The command's exit code.
        reason: Why the run did not record a pass.

    Raises:
        OSError: If the record cannot be written. Any temp file is removed.
    """
    _write_json(
        path,
        {
            "tree": tree,
            "name": name,
            "command": list(command),
            "exit_code": exit_code,
            "reason": reason,
        },
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    """Write a timestamped JSON record via a temp file and rename, so readers never see half."""
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    payload = {**payload, "timestamp": timestamp}
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
    return sorted({record["name"] for record in _records(common_dir, tree, suffix="")})


def missed_records(common_dir: Path, tree: str) -> list[dict[str, Any]]:
    """List the gates that ran on a tree without passing, for reporting what would run.

    A gate whose marker exists on the tree is left out, since a later pass supersedes the
    miss. This holds for markers without JSON content too, because those still skip.

    Args:
        common_dir: Absolute path to the git common directory.
        tree: Git tree hash to match.

    Returns:
        Each miss record's JSON content, sorted by gate name.
    """
    records = [
        record
        for record in _records(common_dir, tree, suffix=MISS_SUFFIX)
        if not marker_exists(marker_path(common_dir, tree, record["name"]))
    ]
    return sorted(records, key=lambda record: record["name"])


def miss_record(common_dir: Path, tree: str, name: str) -> dict[str, Any] | None:
    """Read one gate's miss record on a tree.

    Args:
        common_dir: Absolute path to the git common directory.
        tree: Git tree hash.
        name: Gate name.

    Returns:
        The record's JSON content, or None when it is missing, unreadable, or does not
        match the tree and name.
    """
    path = miss_path(common_dir, tree, name)
    data = _read_record(path)
    if data is None or data.get("tree") != tree or data.get("name") != name:
        return None
    return data


def marker_exists(path: Path) -> bool:
    """Return True only when the path is known to exist."""
    try:
        return path.exists()
    except OSError:
        return False


def _read_record(path: Path) -> dict[str, Any] | None:
    """Parse a JSON object from a record file, or return None when it is not one."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _records(common_dir: Path, tree: str, *, suffix: str) -> list[dict[str, Any]]:
    """Read the records for a tree whose filename is the key of their own name plus suffix."""
    try:
        entries = list(marker_dir(common_dir).iterdir())
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for entry in entries:
        if entry.name.startswith(TEMP_PREFIX) or not entry.name.endswith(suffix):
            continue
        data = _read_record(entry)
        if data is None:
            continue
        name = data.get("name")
        if (
            data.get("tree") == tree
            and isinstance(name, str)
            and f"{marker_key(tree, name)}{suffix}" == entry.name
        ):
            records.append(data)
    return records


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
    """Delete every marker and miss record, and the marker directory.

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
        if not entry.name.startswith(TEMP_PREFIX) and not entry.name.endswith(MISS_SUFFIX):
            count += 1
    try:
        directory.rmdir()
    except OSError:
        shutil.rmtree(directory, ignore_errors=True)
    if directory.exists():
        msg = f"could not remove {directory}"
        raise OSError(msg)
    return count
