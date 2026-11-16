"""Marker files that record a gate command passing on a git tree."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

MARKER_DIRNAME = "gate-cache"
TEMP_PREFIX = ".tmp-"
MISS_SUFFIX = ".miss"
# Records hold a command line, which the OS caps at a few MiB. The cap keeps a stray large
# file from being read in full.
MAX_RECORD_BYTES = 16 * 1024 * 1024
_DAY_SECONDS = 86400
# No gate runs this long, so a larger stored value is corrupt.
MAX_DURATION_SECONDS = 30 * _DAY_SECONDS


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


def scope_fields(paths: Sequence[str], full_tree: str | None) -> dict[str, object]:
    """Return the record keys that describe a scoped gate, or none for an unscoped one.

    Args:
        paths: Pathspecs of a scoped gate, or empty for an unscoped one.
        full_tree: Whole working-copy tree of the run.

    Returns:
        The `paths` and `full_tree` keys, or an empty dict when paths is empty.
    """
    return {"paths": list(paths), "full_tree": full_tree} if paths else {}


def write_marker(
    path: Path,
    *,
    tree: str,
    name: str,
    command: Sequence[str],
    paths: Sequence[str] = (),
    full_tree: str | None = None,
    duration: float | None = None,
) -> None:
    """Atomically write a marker file.

    Args:
        path: Destination marker path; its parent directory is created if needed.
        tree: Git tree hash, or scope value, the command passed on.
        name: Gate name.
        command: The command that passed.
        paths: Pathspecs of a scoped gate, or empty for an unscoped one.
        full_tree: Whole working-copy tree of a scoped gate's run.
        duration: Seconds the command ran, shown on later skips. Omitted when None.

    Raises:
        OSError: If the marker cannot be written. Any temp file is removed.
    """
    payload: dict[str, object] = {
        "tree": tree,
        "name": name,
        "command": list(command),
        **scope_fields(paths, full_tree),
    }
    if duration is not None:
        payload["duration"] = round(duration, 3)
    _write_json(path, payload)


def write_miss(  # noqa: PLR0913
    path: Path,
    *,
    tree: str,
    name: str,
    command: Sequence[str],
    exit_code: int,
    reason: str,
    paths: Sequence[str] = (),
    full_tree: str | None = None,
) -> None:
    """Atomically record that a gate ran on a tree and did not pass.

    Args:
        path: Destination miss record path; its parent directory is created if needed.
        tree: Git tree hash, or scope value, the command ran on.
        name: Gate name.
        command: The command that ran.
        exit_code: The command's exit code.
        reason: Why the run did not record a pass.
        paths: Pathspecs of a scoped gate, or empty for an unscoped one.
        full_tree: Whole working-copy tree of a scoped gate's run.

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
            **scope_fields(paths, full_tree),
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
        # O_NONBLOCK keeps a FIFO from blocking the open; fstat on the open file then rejects it.
        with open(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb") as handle:  # noqa: PTH123
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_RECORD_BYTES:
                return None
            raw = handle.read(MAX_RECORD_BYTES + 1)
        if len(raw) > MAX_RECORD_BYTES:
            return None
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def marker_duration(path: Path) -> float | None:
    """Read how long the recorded pass ran, to report the time a skip saves.

    Markers from other tools or older versions may lack the field, so any problem
    yields None rather than an error.

    Args:
        path: Marker file to read.

    Returns:
        The duration in seconds, or None when the marker has no usable value.
    """
    record = _read_record(path)
    value = record.get("duration") if record is not None else None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    # The range check also rejects NaN, infinity, and ints too large for a float.
    if not 0 <= value <= MAX_DURATION_SECONDS:
        return None
    return float(value)


@dataclass(frozen=True)
class RecordIndex:
    """Every finished marker and miss record of a repository, read from disk once.

    Status asks several questions of the same directory, such as which gates passed on the
    tree and on each scope, so one scan answers them all.

    Attributes:
        common_dir: Absolute path to the git common directory.
        entries: Each record file with its parsed JSON content.
    """

    common_dir: Path
    entries: tuple[tuple[Path, dict[str, Any]], ...]

    @classmethod
    def load(cls, common_dir: Path) -> RecordIndex:
        """Read every finished record file, skipping temp files and unparsable content.

        Args:
            common_dir: Absolute path to the git common directory.

        Returns:
            The index, empty when the marker directory is missing or unreadable.
        """
        try:
            paths = list(marker_dir(common_dir).iterdir())
        except OSError:
            paths = []
        entries = []
        for path in paths:
            if path.name.startswith(TEMP_PREFIX):
                continue
            data = _read_record(path)
            if data is not None:
                entries.append((path, data))
        return cls(common_dir=common_dir, entries=tuple(entries))

    def passed_names(self, *trees: str) -> list[str]:
        """List the gates with a recorded pass on any of the trees, for reporting what would skip.

        Marker filenames are one-way hashes, so names come from each marker's JSON content.
        A file whose content is missing, unreadable, or does not hash to its own filename is
        left out. Markers written by other tools without that content still count for skips
        but cannot be listed.

        Args:
            *trees: Git tree hashes or scope values to match.

        Returns:
            Sorted, unique gate names.
        """
        return sorted({record["name"] for record in self._matching(trees, suffix="")})

    def missed_records(self, *trees: str) -> list[dict[str, Any]]:
        """List the gates that ran on any of the trees without passing.

        A gate whose marker exists on the tree is left out, since a later pass supersedes the
        miss. This holds for markers without JSON content too, because those still skip.

        Args:
            *trees: Git tree hashes or scope values to match.

        Returns:
            Each miss record's JSON content, sorted by gate name.
        """
        records = [
            record
            for record in self._matching(trees, suffix=MISS_SUFFIX)
            if not marker_exists(marker_path(self.common_dir, record["tree"], record["name"]))
        ]
        return sorted(records, key=lambda record: record["name"])

    def scoped_path_sets(self) -> list[tuple[str, ...]]:
        """List each distinct pathspec list that scoped gates were recorded with.

        A scope cannot be reversed into its paths, so status recomputes each listed scope on
        the current content to find the scoped gates that match it.

        Returns:
            The distinct pathspec lists, sorted.
        """
        found: set[tuple[str, ...]] = set()
        for _, data in self.entries:
            paths = data.get("paths")
            if isinstance(paths, list) and paths and all(isinstance(p, str) and p for p in paths):
                found.add(tuple(paths))
        return sorted(found)

    def _matching(self, trees: Collection[str], *, suffix: str) -> list[dict[str, Any]]:
        """Return the records for the trees whose filename is the key of their own name."""
        return [
            data
            for path, data in self.entries
            if isinstance(tree := data.get("tree"), str)
            and tree in trees
            and isinstance(name := data.get("name"), str)
            and path.name == f"{marker_key(tree, name)}{suffix}"
        ]


def passed_names(common_dir: Path, *trees: str) -> list[str]:
    """List the gates with a recorded pass on any of the trees; see RecordIndex.passed_names.

    Args:
        common_dir: Absolute path to the git common directory.
        *trees: Git tree hashes or scope values to match.

    Returns:
        Sorted, unique gate names.
    """
    return RecordIndex.load(common_dir).passed_names(*trees)


def missed_records(common_dir: Path, *trees: str) -> list[dict[str, Any]]:
    """List the gates that ran on any of the trees without passing; see RecordIndex.

    Args:
        common_dir: Absolute path to the git common directory.
        *trees: Git tree hashes or scope values to match.

    Returns:
        Each miss record's JSON content, sorted by gate name.
    """
    return RecordIndex.load(common_dir).missed_records(*trees)


def prune_markers(directory: Path, *, max_age_days: int = 30, now: float | None = None) -> None:
    """Delete markers older than the cutoff, ignoring every filesystem error.

    Args:
        directory: Marker directory to prune.
        max_age_days: Age in days beyond which a file is deleted.
        now: Current epoch time; defaults to the system clock.
    """
    cutoff = (time.time() if now is None else now) - max_age_days * _DAY_SECONDS
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
