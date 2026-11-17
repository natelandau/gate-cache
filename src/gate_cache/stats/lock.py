"""A single-instance lock on the stats state directory, held by the dashboard and `stats clear`."""

from __future__ import annotations

import contextlib
import fcntl
import os
from typing import TYPE_CHECKING, Self

from gate_cache.stats.config import STATE_DIR_MODE

if TYPE_CHECKING:
    from pathlib import Path

_LOCK_NAME = "dashboard.lock"
_URL_NAME = "dashboard.url"


class InstanceLock:
    """An exclusive advisory lock on the state directory, held until released."""

    def __init__(self, state: Path, fd: int) -> None:
        """Wrap a locked file descriptor."""
        self._state = state
        self._fd: int | None = fd

    @classmethod
    def acquire(cls, state: Path) -> Self | None:
        """Take the lock without blocking.

        Args:
            state: The stats state directory; created when missing.

        Returns:
            The held lock, or None when another process holds it.

        Raises:
            OSError: When the state directory or lock file cannot be used.
        """
        state.mkdir(mode=STATE_DIR_MODE, parents=True, exist_ok=True)
        fd = os.open(state / _LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return None
        # A URL left by a crashed holder is stale once the lock is ours.
        try:
            (state / _URL_NAME).unlink(missing_ok=True)
        except OSError:
            os.close(fd)
            raise
        return cls(state, fd)

    def write_url(self, url: str) -> None:
        """Publish the URL of the running dashboard."""
        (self._state / _URL_NAME).write_text(url, encoding="utf-8")

    def release(self) -> None:
        """Remove the published URL and drop the lock."""
        if self._fd is None:
            return
        with contextlib.suppress(OSError):
            (self._state / _URL_NAME).unlink(missing_ok=True)
        os.close(self._fd)  # closing the descriptor drops the flock
        self._fd = None


def running_url(state: Path) -> str | None:
    """Return the URL published by the running dashboard, or None when unknown."""
    try:
        return (state / _URL_NAME).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None
