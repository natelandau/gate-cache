"""A single-instance lock on the stats state directory, held by the dashboard and `stats clear`."""

from __future__ import annotations

import contextlib
import fcntl
import os
import re
from typing import TYPE_CHECKING, Self

from gate_cache.safe_files import ensure_private_dir
from gate_cache.stats.config import DASHBOARD_HOST

if TYPE_CHECKING:
    from pathlib import Path

_LOCK_NAME = "dashboard.lock"
_URL_NAME = "dashboard.url"
_LOOPBACK_URL = re.compile(rf"http://{re.escape(DASHBOARD_HOST)}:(?P<port>[0-9]{{1,5}})/?")
_MAX_PORT = 65535


class InstanceLock:
    """An exclusive advisory lock on the state directory, held until released."""

    def __init__(self, state: Path, fd: int) -> None:
        """Wrap a locked file descriptor."""
        self._state = state
        self._fd: int | None = fd
        self._wrote_url = False

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
        ensure_private_dir(state)
        fd = os.open(state / _LOCK_NAME, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
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
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
        fd = os.open(self._state / _URL_NAME, flags, 0o600)
        try:
            os.write(fd, url.encode())
        finally:
            os.close(fd)
        self._wrote_url = True

    def release(self) -> None:
        """Drop the lock, removing the URL only when this holder published it."""
        if self._fd is None:
            return
        if self._wrote_url:
            with contextlib.suppress(OSError):
                (self._state / _URL_NAME).unlink(missing_ok=True)
        os.close(self._fd)  # closing the descriptor drops the flock
        self._fd = None


def running_url(state: Path) -> str | None:
    """Return the URL published by the running dashboard, or None when unknown.

    Only a loopback HTTP address counts, since the URL is opened in a browser and anything
    with write access to the file could put another kind of address there.
    """
    try:
        url = (state / _URL_NAME).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    match = _LOOPBACK_URL.fullmatch(url)
    if match is None or not 1 <= int(match["port"]) <= _MAX_PORT:
        return None
    return url
