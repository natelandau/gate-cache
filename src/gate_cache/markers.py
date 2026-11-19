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

from gate_cache.stats.gates import gate_of

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

MARKER_DIRNAME = "gate-cache"
TEMP_PREFIX = ".tmp-"
MISS_SUFFIX = ".miss"
# Records hold a command line, which the OS caps at a few MiB. The cap keeps a stray large
# file from being read in full.
MAX_RECORD_BYTES = 16 * 1024 * 1024
DAY_SECONDS = 86400
# No gate runs this long, so a larger stored value is corrupt.
MAX_DURATION_SECONDS = 30 * DAY_SECONDS


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


def utc_timestamp(moment: float | datetime) -> str:
    """Format a moment as ISO 8601 UTC with seconds precision and a `Z` suffix.

    Args:
        moment: Unix seconds, or an aware datetime.

    Returns:
        str: The timestamp, such as `2026-11-18T12:00:00Z`.
    """
    if not isinstance(moment, datetime):
        moment = datetime.fromtimestamp(moment, UTC)
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    """Write a JSON record stamped with the current time."""
    write_json_atomic(path, {**payload, "timestamp": utc_timestamp(datetime.now(UTC))})


def write_json_atomic(path: Path, value: object) -> None:
    """Write JSON via a temp file and rename, so readers never see half a file.

    Args:
        path: The file to write; its directory is created when missing.
        value: The JSON value to write.

    Raises:
        OSError: If the file cannot be written. Any temp file is removed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=TEMP_PREFIX, delete=False
        ) as tmp:
            tmp_name = tmp.name
            json.dump(value, tmp)
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
    data = read_record(path)
    if data is None or data.get("tree") != tree or data.get("name") != name:
        return None
    return data


def marker_exists(path: Path, *, max_age_days: int, now: float | None = None) -> bool:
    """Return True only when the marker is known to exist and has not expired.

    A marker expires at the same age that pruning deletes it, so the age limit holds even
    before a later run prunes the marker.

    Args:
        path: The marker file.
        max_age_days: Age in days past which the marker no longer counts as a pass.
        now: Current epoch time; defaults to the system clock.

    Returns:
        True when the marker exists and is younger than the age limit.
    """
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return False
    return not _expired(mtime, max_age_days=max_age_days, now=now)


def _expired(mtime: float, *, max_age_days: int, now: float | None = None) -> bool:
    """Return whether a file last written at mtime is older than the age limit."""
    return mtime < (time.time() if now is None else now) - max_age_days * DAY_SECONDS


def read_json(path: Path) -> object:
    """Parse JSON from a small file, refusing FIFOs and oversized files.

    Args:
        path: The file to read.

    Returns:
        The parsed value, or None when the file is missing, not a regular file, too
        large, or not JSON.
    """
    try:
        # O_NONBLOCK keeps a FIFO from blocking the open; fstat on the open file then rejects it.
        with open(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb") as handle:  # noqa: PTH123
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_RECORD_BYTES:
                return None
            raw = handle.read(MAX_RECORD_BYTES + 1)
        if len(raw) > MAX_RECORD_BYTES:
            return None
        return json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return None


def read_record(path: Path) -> dict[str, Any] | None:
    """Parse a JSON object from a small record file.

    Args:
        path: The record file to read.

    Returns:
        The parsed object, or None when `read_json` gives anything but a JSON object.
    """
    data = read_json(path)
    return data if isinstance(data, dict) else None


def valid_duration(value: object) -> float | None:
    """Return a stored run time as seconds, or None when it is not a plausible one.

    Args:
        value: A value read from JSON.

    Returns:
        The duration in seconds, or None for a non-number, a bool, or a value out of range.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    # The range check also rejects NaN, infinity, and ints too large for a float.
    if not 0 <= value <= MAX_DURATION_SECONDS:
        return None
    return float(value)


def marker_duration(path: Path) -> float | None:
    """Read how long the recorded pass ran, to report the time a skip saves.

    Markers from other tools or older versions may lack the field, so any problem
    yields None rather than an error.

    Args:
        path: Marker file to read.

    Returns:
        The duration in seconds, or None when the marker has no usable value.
    """
    record = read_record(path)
    return valid_duration(record.get("duration")) if record is not None else None


@dataclass(frozen=True)
class RecordIndex:
    """Every finished marker and miss record of a repository, read from disk once.

    Status asks several questions of the same directory, such as which gates passed on the
    tree and on each scope, so one scan answers them all.

    Attributes:
        common_dir: Absolute path to the git common directory.
        entries: Each unexpired record file with its parsed JSON content.
        max_age_days: Age in days past which a record no longer counts.
    """

    common_dir: Path
    entries: tuple[tuple[Path, dict[str, Any]], ...]
    max_age_days: int

    @classmethod
    def load(cls, common_dir: Path, *, max_age_days: int) -> RecordIndex:
        """Read every finished record file, skipping temp files, expired records, and bad content.

        Args:
            common_dir: Absolute path to the git common directory.
            max_age_days: Age in days past which a record no longer counts.

        Returns:
            The index, empty when the marker directory is missing or unreadable.
        """
        try:
            paths = list(marker_dir(common_dir).iterdir())
        except OSError:
            paths = []
        entries = []
        for path in paths:
            if path.name.startswith(TEMP_PREFIX) or not marker_exists(
                path, max_age_days=max_age_days
            ):
                continue
            data = read_record(path)
            if data is not None:
                entries.append((path, data))
        return cls(common_dir=common_dir, entries=tuple(entries), max_age_days=max_age_days)

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
            if not marker_exists(
                marker_path(self.common_dir, record["tree"], record["name"]),
                max_age_days=self.max_age_days,
            )
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
            if data.get("tree") in trees and _own_name(path, data, suffix=suffix) is not None
        ]


def passed_names(common_dir: Path, *trees: str, max_age_days: int) -> list[str]:
    """List the gates with a recorded pass on any of the trees; see RecordIndex.passed_names.

    Args:
        common_dir: Absolute path to the git common directory.
        *trees: Git tree hashes or scope values to match.
        max_age_days: Age in days past which a record no longer counts.

    Returns:
        Sorted, unique gate names.
    """
    return RecordIndex.load(common_dir, max_age_days=max_age_days).passed_names(*trees)


def missed_records(common_dir: Path, *trees: str, max_age_days: int) -> list[dict[str, Any]]:
    """List the gates that ran on any of the trees without passing; see RecordIndex.

    Args:
        common_dir: Absolute path to the git common directory.
        *trees: Git tree hashes or scope values to match.
        max_age_days: Age in days past which a record no longer counts.

    Returns:
        Each miss record's JSON content, sorted by gate name.
    """
    return RecordIndex.load(common_dir, max_age_days=max_age_days).missed_records(*trees)


def prune_markers(directory: Path, *, max_age_days: int = 30, now: float | None = None) -> None:
    """Delete markers older than the cutoff, ignoring every filesystem error.

    Args:
        directory: Marker directory to prune.
        max_age_days: Age in days beyond which a file is deleted.
        now: Current epoch time; defaults to the system clock.
    """
    try:
        for entry in directory.iterdir():
            with contextlib.suppress(OSError):
                if (
                    entry.is_file()
                    and not entry.is_symlink()
                    and _expired(entry.stat().st_mtime, max_age_days=max_age_days, now=now)
                ):
                    entry.unlink()
    except OSError:
        return


@dataclass(frozen=True)
class MarkerSelection:
    """The marker and miss record files that a clear deletes, found in one scan.

    Attributes:
        gate: The gate the selection is limited to, or None for every record.
        passes: Marker files, each a recorded pass.
        misses: Miss record files, each a failed run.
        names: The gate names read from the selected files, sorted and unique.
    """

    gate: str | None
    passes: tuple[Path, ...]
    misses: tuple[Path, ...]
    names: tuple[str, ...]


def select_markers(common_dir: Path, *, gate: str | None = None) -> MarkerSelection:
    """Find the records a clear deletes, so the warning and the delete agree on them.

    Without `gate`, every record counts, including markers from other tools whose content
    cannot be read. With `gate`, only records whose content names that gate, or one of its
    keyed names such as `gate@key`, count, since an unreadable marker's gate is unknown.

    Args:
        common_dir: Absolute path to the git common directory.
        gate: The gate whose records to select. None selects every record.

    Returns:
        The selected files and the gate names they hold.
    """
    try:
        entries = sorted(marker_dir(common_dir).iterdir())
    except OSError:
        entries = []
    passes: list[Path] = []
    misses: list[Path] = []
    names: set[str] = set()
    for path in entries:
        if path.name.startswith(TEMP_PREFIX) or not path.is_file() or path.is_symlink():
            continue
        is_miss = path.name.endswith(MISS_SUFFIX)
        name = _own_name(path, read_record(path), suffix=MISS_SUFFIX if is_miss else "")
        if gate is not None and (name is None or (name != gate and gate_of(name) != gate)):
            continue
        if name is not None:
            names.add(name)
        (misses if is_miss else passes).append(path)
    return MarkerSelection(
        gate=gate, passes=tuple(passes), misses=tuple(misses), names=tuple(sorted(names))
    )


def _own_name(path: Path, data: dict[str, Any] | None, *, suffix: str) -> str | None:
    """Return the gate name a record holds, or None unless the record hashes to its filename.

    A marker filename is a one-way hash, so only content that hashes back to it can say
    which gate the file belongs to.
    """
    if data is None:
        return None
    name, tree = data.get("name"), data.get("tree")
    if (
        isinstance(name, str)
        and isinstance(tree, str)
        and path.name == f"{marker_key(tree, name)}{suffix}"
    ):
        return name
    return None


def delete_markers(selection: MarkerSelection) -> int:
    """Delete the selected records, tolerating files that a concurrent run already removed.

    Args:
        selection: The records to delete, from `select_markers`.

    Returns:
        The number of markers deleted, not counting miss records.

    Raises:
        OSError: If a file exists but cannot be deleted.
    """
    count = 0
    for path in selection.passes:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
            count += 1
    for path in selection.misses:
        path.unlink(missing_ok=True)
    return count


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
