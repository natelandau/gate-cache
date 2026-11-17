"""Tests for the per-gate lock that coalesces concurrent runs."""

import os
import threading
import time
from pathlib import Path

import pytest

from gate_cache.gate_lock import (
    HELD_ENV,
    GateLock,
    Holder,
    held_by_ancestor,
    held_env,
    lock_path,
    prune_locks,
    read_holder,
)
from gate_cache.markers import marker_key

_DAY = 86400


@pytest.fixture
def path(tmp_path: Path) -> Path:
    """Return a lock path inside a fresh lock directory."""
    return lock_path(tmp_path, "tree", "name")


def test_lock_path_uses_marker_key(tmp_path: Path) -> None:
    """The lock file is named after the marker key."""
    expected = tmp_path / "gate-cache-locks" / f"{marker_key('t', 'n')}.lock"
    assert lock_path(tmp_path, "t", "n") == expected


def test_second_acquire_returns_none_until_release(path: Path) -> None:
    """A held lock blocks a second open file description until released."""
    first = GateLock.try_acquire(path)
    assert first is not None
    assert GateLock.try_acquire(path) is None
    first.release()
    second = GateLock.try_acquire(path)
    assert second is not None
    second.release()


def test_wait_returns_lock_when_released(path: Path) -> None:
    """Waiting returns the lock soon after the holder releases."""
    lock = GateLock.try_acquire(path)
    assert lock is not None
    timer = threading.Timer(0.3, lock.release)
    timer.start()
    start = time.monotonic()
    waited = GateLock.wait(path, timeout=5)
    timer.join()
    assert waited is not None
    assert time.monotonic() - start < 2
    waited.release()


def test_wait_times_out(path: Path) -> None:
    """Waiting gives up with None after the timeout."""
    lock = GateLock.try_acquire(path)
    assert lock is not None
    start = time.monotonic()
    assert GateLock.wait(path, timeout=0.3) is None
    assert time.monotonic() - start >= 0.3
    lock.release()


def test_acquire_retries_when_file_replaced(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A lock on an unlinked file is dropped and the new file is locked."""
    path.parent.mkdir(parents=True)
    path.touch()
    real_open = os.open
    replaced = False

    def replacing_open(p: str | Path, flags: int, mode: int = 0o777) -> int:
        fd = real_open(p, flags, mode)
        nonlocal replaced
        if not replaced:
            replaced = True
            Path(p).unlink()
            Path(p).touch()
        return fd

    monkeypatch.setattr(os, "open", replacing_open)
    lock = GateLock.try_acquire(path)
    assert lock is not None
    assert replaced
    # The lock sits on the file now at the path, so a second attempt is refused.
    assert GateLock.try_acquire(path) is None
    lock.release()


def test_acquire_raises_when_file_keeps_being_replaced(
    path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file replaced on every attempt raises, so the caller never reads it as held."""
    path.parent.mkdir(parents=True)
    path.touch()
    real_open = os.open
    opened = 0

    def replacing_open(p: str | Path, flags: int, mode: int = 0o777) -> int:
        nonlocal opened
        opened += 1
        fd = real_open(p, flags, mode)
        Path(p).unlink()
        os.close(real_open(p, os.O_CREAT | os.O_WRONLY, 0o644))
        return fd

    monkeypatch.setattr(os, "open", replacing_open)
    with pytest.raises(OSError, match="was replaced"):
        GateLock.try_acquire(path)
    assert opened > 1
    monkeypatch.undo()
    # Every failed attempt released its lock.
    lock = GateLock.try_acquire(path)
    assert lock is not None
    lock.release()


def test_holder_round_trip(path: Path) -> None:
    """The holder record reads back what was written."""
    lock = GateLock.try_acquire(path)
    assert lock is not None
    lock.write_holder(Path("/w"))
    holder = read_holder(path)
    assert holder is not None
    assert holder == Holder(worktree="/w", pid=os.getpid(), started=holder.started)
    assert isinstance(holder.started, float)
    lock.release()


def test_read_holder_bad_json_returns_none(path: Path) -> None:
    """Malformed or missing holder data yields None."""
    assert read_holder(path) is None
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    assert read_holder(path) is None


def test_held_env_set_and_restored(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The held block exports the lock name and restores the prior value."""
    with held_env(path):
        assert path.name in os.environ[HELD_ENV].split(":")
    assert HELD_ENV not in os.environ
    monkeypatch.setenv(HELD_ENV, "other.lock")
    with held_env(path):
        assert os.environ[HELD_ENV].split(":") == ["other.lock", path.name]
    assert os.environ[HELD_ENV] == "other.lock"


def test_held_by_ancestor(path: Path) -> None:
    """The ancestor check matches on the lock file name."""
    assert held_by_ancestor(path, {HELD_ENV: f"x.lock:{path.name}"})
    assert not held_by_ancestor(path, {HELD_ENV: "x.lock"})
    assert not held_by_ancestor(path, {})


def test_prune_skips_held_and_deletes_old_free(tmp_path: Path) -> None:
    """Pruning removes only old lock files that nobody holds."""
    held = lock_path(tmp_path, "t", "held")
    free = lock_path(tmp_path, "t", "free")
    lock = GateLock.try_acquire(held)
    assert lock is not None
    freed = GateLock.try_acquire(free)
    assert freed is not None
    freed.release()
    old = time.time() - 40 * _DAY
    for p in (held, free):
        os.utime(p, (old, old))
    prune_locks(tmp_path, max_age_days=30)
    assert held.exists()
    assert not free.exists()
    lock.release()


def test_release_never_unlinks(path: Path) -> None:
    """Releasing leaves the file in place and is idempotent."""
    lock = GateLock.try_acquire(path)
    assert lock is not None
    lock.release()
    lock.release()
    assert path.exists()


def test_prune_keeps_free_file_newer_than_cutoff(tmp_path: Path) -> None:
    """A recent free lock file survives pruning."""
    recent = lock_path(tmp_path, "t", "recent")
    lock = GateLock.try_acquire(recent)
    assert lock is not None
    lock.release()
    prune_locks(tmp_path, max_age_days=30)
    assert recent.exists()


def test_prune_without_lock_dir_is_noop(tmp_path: Path) -> None:
    """Pruning a common dir with no lock directory does nothing."""
    prune_locks(tmp_path, max_age_days=30)
    assert not (tmp_path / "gate-cache-locks").exists()


def test_wait_zero_timeout_tries_once(path: Path) -> None:
    """A zero timeout makes one attempt and gives up when the lock is held."""
    free = GateLock.wait(path, timeout=0)
    assert free is not None
    assert GateLock.wait(path, timeout=0) is None
    free.release()


def test_read_holder_rejects_bool_started(path: Path) -> None:
    """A boolean start time is malformed, as with the pid."""
    path.parent.mkdir(parents=True)
    path.write_text('{"worktree": null, "pid": 1, "started": true}')
    assert read_holder(path) is None


def test_wait_keeps_one_file_open_while_polling(
    path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Polling retries the lock on the open file instead of reopening it each time."""
    monkeypatch.setattr("gate_cache.gate_lock.POLL_INTERVAL", 0.01)
    lock = GateLock.try_acquire(path)
    assert lock is not None
    real_open = os.open
    opened = 0

    def counting_open(p: str | Path, flags: int, mode: int = 0o777) -> int:
        nonlocal opened
        opened += 1
        return real_open(p, flags, mode)

    monkeypatch.setattr(os, "open", counting_open)
    assert GateLock.wait(path, timeout=0.1) is None
    assert opened == 1
    lock.release()


def test_wait_reopens_a_replaced_file(path: Path) -> None:
    """A lock taken on a file that pruning replaced is dropped for the file now at the path."""
    lock = GateLock.try_acquire(path)
    assert lock is not None

    def replace_and_release() -> None:
        path.unlink()
        lock.release()

    timer = threading.Timer(0.3, replace_and_release)
    timer.start()
    waited = GateLock.wait(path, timeout=5)
    timer.join()
    assert waited is not None
    # The lock sits on the file now at the path, so a second attempt is refused.
    assert GateLock.try_acquire(path) is None
    waited.release()


def test_acquire_creates_missing_directory(tmp_path: Path) -> None:
    """The lock directory is created on the first lock."""
    path = lock_path(tmp_path / "missing", "t", "n")
    lock = GateLock.try_acquire(path)
    assert lock is not None
    assert path.exists()
    lock.release()


def test_write_holder_after_release_is_noop(path: Path) -> None:
    """A released lock writes no holder record."""
    lock = GateLock.try_acquire(path)
    assert lock is not None
    lock.release()
    lock.write_holder(Path("/w"))
    assert read_holder(path) is None


def test_read_holder_rejects_missing_field(path: Path) -> None:
    """A holder record without every field is malformed."""
    path.parent.mkdir(parents=True)
    path.write_text('{"pid": 1, "started": 1.0}')
    assert read_holder(path) is None


def test_read_holder_refuses_fifo(path: Path) -> None:
    """A FIFO at the lock path reads as no holder instead of blocking."""
    path.parent.mkdir(parents=True)
    os.mkfifo(path)
    assert read_holder(path) is None


def test_prune_runs_at_most_once_a_day(tmp_path: Path) -> None:
    """A prune within a day of the last one skips the scan; a later one runs."""
    free = lock_path(tmp_path, "t", "free")
    lock = GateLock.try_acquire(free)
    assert lock is not None
    lock.release()
    now = time.time()
    prune_locks(tmp_path, max_age_days=30, now=now)
    old = now - 40 * _DAY
    os.utime(free, (old, old))

    prune_locks(tmp_path, max_age_days=30, now=now + _DAY / 2)
    assert free.exists()

    prune_locks(tmp_path, max_age_days=30, now=now + _DAY)
    assert not free.exists()
