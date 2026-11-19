"""Recent run times of each gate, so a run can say how long it usually takes."""

from __future__ import annotations

import contextlib
import hashlib
from typing import TYPE_CHECKING

from gate_cache.markers import read_json, valid_duration, write_json_atomic

if TYPE_CHECKING:
    from pathlib import Path

# Outside the marker directory, whose contents are a public contract.
DURATIONS_DIRNAME = "gate-cache-durations"
KEPT_DURATIONS = 5


def durations_dir(common_dir: Path) -> Path:
    """Return the directory that holds every gate's recent run times.

    Args:
        common_dir: Absolute path to the git common directory.

    Returns:
        The durations directory.
    """
    return common_dir / DURATIONS_DIRNAME


def durations_path(common_dir: Path, name: str) -> Path:
    """Return the file of one gate's recent run times, shared by every worktree.

    Args:
        common_dir: Absolute path to the git common directory.
        name: Gate name.

    Returns:
        The file path, named by the SHA-256 of the gate name.
    """
    digest = hashlib.sha256(name.encode()).hexdigest()
    return durations_dir(common_dir) / f"{digest}.json"


def _recent(path: Path) -> list[float]:
    """Read the newest valid run times, oldest first; any problem gives an empty list."""
    data = read_json(path)
    if not isinstance(data, list):
        return []
    values = [valid_duration(item) for item in data]
    return [value for value in values if value is not None][-KEPT_DURATIONS:]


def usual_duration(path: Path) -> float | None:
    """Return how long a gate usually runs, as the median of its recent run times.

    A median keeps one unusually slow or fast run from moving the estimate.

    Args:
        path: The gate's durations file.

    Returns:
        The median in seconds, or None when no valid run time is stored.
    """
    # Imported here because it costs about 1.5 ms, and skips never need it.
    import statistics

    recent = _recent(path)
    return statistics.median(recent) if recent else None


def record_duration(path: Path, duration: float) -> None:
    """Add a run time to a gate's recent ones, best effort.

    The estimate is advisory, so a write that fails is dropped without a warning.

    Args:
        path: The gate's durations file.
        duration: Seconds the command ran.
    """
    values = [*_recent(path), round(duration, 3)][-KEPT_DURATIONS:]
    with contextlib.suppress(OSError):
        write_json_atomic(path, values)
