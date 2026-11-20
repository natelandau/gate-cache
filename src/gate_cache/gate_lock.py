"""A per-gate lock that lets concurrent runs of the same gate on the same tree take turns."""

from __future__ import annotations

import contextlib
import errno
import fcntl
import json
import os
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from gate_cache.markers import DAY_SECONDS, marker_key, open_own_dir, owned_files, read_record

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping
    from pathlib import Path
    from types import TracebackType

LOCK_DIRNAME = "gate-cache-locks"
HELD_ENV = "GATE_CACHE_HELD_LOCKS"
_LOCK_SUFFIX = ".lock"
_MAX_ATTEMPTS = 5
POLL_INTERVAL = 0.2
_PRUNE_STAMP = ".pruned"
_LOCK_NAME = re.compile(rf"[0-9a-f]{{64}}{re.escape(_LOCK_SUFFIX)}")


def lock_path(common_dir: Path, tree: str, name: str) -> Path:
    """Return the lock file for a gate name on a git tree.

    Args:
        common_dir: Absolute path to the git common directory.
        tree: Git tree hash.
        name: Gate name.

    Returns:
        The lock file path, outside the marker directory.
    """
    return common_dir / LOCK_DIRNAME / f"{marker_key(tree, name)}{_LOCK_SUFFIX}"


@dataclass(frozen=True)
class Holder:
    """The process that holds a gate lock."""

    worktree: str | None
    pid: int
    started: float


def _open(path: Path) -> int:
    """Open the lock file for locking, creating it and its directory when missing.

    Neither the file nor its directory is opened through a symlink, so a link planted in the
    git directory cannot make gate-cache create or truncate a file elsewhere.
    """
    try:
        dir_fd = open_own_dir(path.parent)
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        dir_fd = open_own_dir(path.parent)
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
    try:
        for _ in range(_MAX_ATTEMPTS - 1):
            # macOS can fail a create relative to a directory descriptor with ENOENT while
            # another process creates the same file; the file exists on the next try.
            with contextlib.suppress(FileNotFoundError):
                return os.open(path.name, flags, 0o644, dir_fd=dir_fd)
        return os.open(path.name, flags, 0o644, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def _try_lock(fd: int) -> bool:
    """Take the exclusive lock on an open file without blocking; return whether it was taken."""
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _still_at(fd: int, path: Path) -> bool:
    """Return whether the open file is still the file at path."""
    # Pruning unlinks free files, so a lock on a replaced file guards nothing.
    try:
        return os.fstat(fd).st_ino == path.lstat().st_ino
    except FileNotFoundError:
        return False


class GateLock:
    """An exclusive advisory lock on one gate lock file, held until released."""

    def __init__(self, path: Path, fd: int) -> None:
        """Wrap a locked file descriptor."""
        self._path = path
        self._fd: int | None = fd

    @classmethod
    def try_acquire(cls, path: Path) -> Self | None:
        """Take the lock without blocking.

        Args:
            path: The lock file; it and its directory are created when missing.

        Returns:
            The held lock, or None when another open file description holds it.

        Raises:
            OSError: When the lock file cannot be created or locked, or keeps being
                replaced while it is locked.
        """
        for _ in range(_MAX_ATTEMPTS):
            fd = _open(path)
            try:
                if not _try_lock(fd):
                    os.close(fd)
                    return None
                same = _still_at(fd, path)
            except BaseException:
                os.close(fd)
                raise
            if same:
                return cls(path, fd)
            os.close(fd)
        msg = f"{path} was replaced on each of {_MAX_ATTEMPTS} attempts to lock it"
        raise OSError(msg)

    @classmethod
    def wait(cls, path: Path, *, timeout: float) -> Self | None:
        """Poll for the lock every POLL_INTERVAL seconds until it is free or the timeout passes.

        One file stays open across polls; it is reopened only when pruning replaced it.

        Args:
            path: The lock file.
            timeout: Seconds to wait before giving up.

        Returns:
            The held lock, or None when the timeout passed first.
        """
        deadline = time.monotonic() + timeout
        fd: int | None = _open(path)
        try:
            while True:
                if _try_lock(fd):
                    if _still_at(fd, path):
                        lock, fd = cls(path, fd), None
                        return lock
                    os.close(fd)
                    # Cleared first so a failed reopen does not close the old fd twice.
                    fd = None
                    fd = _open(path)
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                time.sleep(min(POLL_INTERVAL, remaining))
        finally:
            if fd is not None:
                os.close(fd)

    def write_holder(self, worktree: Path | None) -> None:
        """Record who holds the lock so waiters can say what they wait on.

        Args:
            worktree: The worktree root of the holder, when known.
        """
        if self._fd is None:
            return
        record = {
            "worktree": str(worktree) if worktree is not None else None,
            "pid": os.getpid(),
            "started": time.time(),
        }
        with contextlib.suppress(OSError):
            os.ftruncate(self._fd, 0)
            os.pwrite(self._fd, json.dumps(record).encode(), 0)

    def release(self) -> None:
        """Drop the lock; the file stays so waiters keep a stable inode."""
        if self._fd is None:
            return
        os.close(self._fd)
        self._fd = None

    def __enter__(self) -> Self:
        """Return the lock for use in a with block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Release the lock."""
        self.release()


def read_holder(path: Path) -> Holder | None:
    """Read the holder record of a lock file.

    Args:
        path: The lock file.

    Returns:
        The holder, or None when the file is missing, empty, or malformed.
    """
    data = read_record(path)
    if data is None or not {"worktree", "pid", "started"} <= data.keys():
        return None
    worktree, pid, started = data["worktree"], data["pid"], data["started"]
    if (
        not isinstance(worktree, str | None)
        or not isinstance(pid, int)
        or isinstance(pid, bool)
        or isinstance(started, bool)
        or not isinstance(started, int | float)
    ):
        return None
    return Holder(worktree=worktree, pid=pid, started=float(started))


@contextlib.contextmanager
def held_env(path: Path) -> Generator[None]:
    """List a lock file in the nested-call variable, so child gate runs never wait on it.

    A run that waited out the timeout and runs without the lock uses this too, so a
    nested call does not wait another full timeout on the same hung holder.

    Args:
        path: The lock file.

    Yields:
        None, with the variable set until the block exits.
    """
    previous = os.environ.get(HELD_ENV)
    names = [previous, path.name] if previous else [path.name]
    os.environ[HELD_ENV] = ":".join(names)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(HELD_ENV, None)
        else:
            os.environ[HELD_ENV] = previous


def held_by_ancestor(path: Path, environ: Mapping[str, str] | None = None) -> bool:
    """Tell whether a parent gate-cache process already holds this lock.

    A nested call that waited on its own parent would deadlock.

    Args:
        path: The lock file.
        environ: The environment to read; defaults to the process environment.

    Returns:
        True when the lock file name is listed in the nested-call variable.
    """
    env = os.environ if environ is None else environ
    return path.name in env.get(HELD_ENV, "").split(":")


def prune_locks(common_dir: Path, *, max_age_days: int, now: float | None = None) -> None:
    """Delete lock files older than the cutoff that no process holds, at most once a day.

    A stamp file in the lock directory records the last prune, so most runs skip the scan.
    A symlinked lock directory is left alone.

    Args:
        common_dir: Absolute path to the git common directory.
        max_age_days: Age in days past which a free lock file is removed.
        now: The current time in seconds; defaults to the clock.
    """
    now = time.time() if now is None else now
    lock_dir = common_dir / LOCK_DIRNAME
    try:
        fd = open_own_dir(lock_dir)
    except OSError:
        return
    try:
        if _pruned_since(fd, now - DAY_SECONDS):
            return
        with contextlib.suppress(OSError):
            _delete_free_locks(fd, lock_dir, cutoff=now - max_age_days * DAY_SECONDS)
            _stamp(fd, now)
    finally:
        os.close(fd)


def _pruned_since(fd: int, moment: float) -> bool:
    """Return whether the stamp in the open lock directory is newer than moment."""
    try:
        return os.stat(_PRUNE_STAMP, dir_fd=fd, follow_symlinks=False).st_mtime > moment
    except OSError:
        return False


def _delete_free_locks(fd: int, lock_dir: Path, *, cutoff: float) -> None:
    """Delete each lock file in the open directory last written before cutoff that is free."""
    for entry in owned_files(fd, _LOCK_NAME):
        with contextlib.suppress(OSError):
            if entry.stat(follow_symlinks=False).st_mtime >= cutoff:
                continue
            lock = GateLock.try_acquire(lock_dir / entry.name)
            if lock is None:
                continue
            try:
                os.unlink(entry.name, dir_fd=fd)
            finally:
                lock.release()


def _stamp(fd: int, now: float) -> None:
    """Record a prune at now in the open lock directory, never through a symlink."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
    try:
        stamp = os.open(_PRUNE_STAMP, flags, 0o644, dir_fd=fd)
    except OSError as error:
        if error.errno != errno.ELOOP:
            raise
        # Replace a symlink at the stamp, or every later run would scan the directory again.
        os.unlink(_PRUNE_STAMP, dir_fd=fd)
        stamp = os.open(_PRUNE_STAMP, flags, 0o644, dir_fd=fd)
    try:
        os.utime(stamp, (now, now))
    finally:
        os.close(stamp)
