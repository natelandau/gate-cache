"""Provide private, short-lived directories for gate-cache's own git probes."""

from __future__ import annotations

import contextlib
import shutil
import tempfile
import time
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import platformdirs

if TYPE_CHECKING:
    from collections.abc import Generator

SCRATCH_PREFIX = "snap-"
STALE_AFTER_SECONDS = 3600


def runtime_area() -> Path:
    """Return the private directory that holds every scratch directory, creating it if needed.

    Honors XDG_RUNTIME_DIR and falls back to the platform's per-user runtime location.

    Returns:
        The absolute path of the area, with mode 0700.
    """
    # An unset XDG_RUNTIME_DIR is normal in containers and SSH sessions, so the fallback
    # warning would only add noise to gate output.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", platformdirs.RuntimeDirWarning)
        area = platformdirs.user_runtime_path("gate-cache", appauthor=False)
    area.mkdir(mode=0o700, parents=True, exist_ok=True)
    return area


def sweep_stale(area: Path, *, now: float | None = None) -> None:
    """Delete scratch directories that a killed run left behind.

    Only directories older than STALE_AFTER_SECONDS go, so a parallel run's directory survives.

    Args:
        area: Directory holding scratch directories.
        now: Current time in seconds since the epoch; defaults to the clock.
    """
    cutoff = (time.time() if now is None else now) - STALE_AFTER_SECONDS
    with contextlib.suppress(OSError):
        for entry in area.glob(f"{SCRATCH_PREFIX}*"):
            with contextlib.suppress(OSError):
                if entry.stat().st_mtime < cutoff:
                    shutil.rmtree(entry, ignore_errors=True)


@contextmanager
def scratch_dir() -> Generator[Path]:
    """Yield a private directory that is deleted when the block exits, however it exits.

    Yields:
        The path of a new, empty directory inside the runtime area.
    """
    area = runtime_area()
    sweep_stale(area)
    with tempfile.TemporaryDirectory(prefix=SCRATCH_PREFIX, dir=area) as path:
        yield Path(path)
