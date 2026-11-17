"""Tests for the single-instance lock on the stats state directory."""

from pathlib import Path

import pytest

from gate_cache.stats.lock import InstanceLock, running_url


def test_lock_is_exclusive(tmp_path: Path) -> None:
    """A held lock blocks a second acquire until released."""
    first = InstanceLock.acquire(tmp_path)
    assert first is not None
    assert InstanceLock.acquire(tmp_path) is None
    first.write_url("http://127.0.0.1:1")
    assert running_url(tmp_path) == "http://127.0.0.1:1"
    first.release()
    assert running_url(tmp_path) is None
    second = InstanceLock.acquire(tmp_path)
    assert second is not None
    second.release()
    second.release()


def test_stale_url_removed_on_acquire(tmp_path: Path) -> None:
    """A URL left by a crashed dashboard does not survive a fresh acquire."""
    (tmp_path / "dashboard.url").write_text("http://stale")
    lock = InstanceLock.acquire(tmp_path)
    assert lock is not None
    assert running_url(tmp_path) is None
    lock.release()


def test_stale_url_unlink_failure_releases_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An error removing the stale URL raises without leaving the lock held."""
    (tmp_path / "dashboard.url").write_text("x")
    real = Path.unlink

    def fail(self: Path, missing_ok: bool = False) -> None:  # noqa: FBT002
        if self.name == "dashboard.url":
            raise PermissionError(13, "denied")
        real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail)
    with pytest.raises(OSError, match="denied"):
        InstanceLock.acquire(tmp_path)
    monkeypatch.setattr(Path, "unlink", real)
    again = InstanceLock.acquire(tmp_path)
    assert again is not None
    again.release()
