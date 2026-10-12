"""Tests for the private temp area."""

import os
import stat
import time
from pathlib import Path

import platformdirs
import pytest

from gate_cache.scratch import (
    SCRATCH_PREFIX,
    STALE_AFTER_SECONDS,
    runtime_area,
    scratch_dir,
    sweep_stale,
)


def test_runtime_area_honors_xdg(git_env: Path, tmp_path: Path) -> None:
    """The area lives under XDG_RUNTIME_DIR and is private."""
    area = runtime_area()
    assert area == tmp_path / "run" / "gate-cache"
    assert stat.S_IMODE(area.stat().st_mode) == 0o700


def test_runtime_area_hides_warning(
    git_env: Path, monkeypatch: pytest.MonkeyPatch, recwarn: pytest.WarningsRecorder
) -> None:
    """An unset XDG_RUNTIME_DIR does not surface platformdirs' warning."""
    monkeypatch.delenv("XDG_RUNTIME_DIR")
    runtime_area()
    assert not [w for w in recwarn if issubclass(w.category, platformdirs.RuntimeDirWarning)]


def test_scratch_dir_is_removed_after_use(git_env: Path) -> None:
    """The per-snapshot directory is deleted when the block ends."""
    with scratch_dir() as path:
        assert path.is_dir()
        assert path.name.startswith(SCRATCH_PREFIX)
        assert path.parent == runtime_area()
    assert not path.exists()


def test_scratch_dir_is_removed_after_keyboard_interrupt(git_env: Path) -> None:
    """Ctrl-C inside the block still deletes the directory."""
    with pytest.raises(KeyboardInterrupt), scratch_dir() as path:
        raise KeyboardInterrupt
    assert not path.exists()


def test_scratch_dir_sweeps_stale_siblings(git_env: Path) -> None:
    """Opening a scratch dir removes orphans left by killed runs."""
    stale = runtime_area() / f"{SCRATCH_PREFIX}orphan"
    stale.mkdir()
    old = time.time() - STALE_AFTER_SECONDS - 60
    os.utime(stale, (old, old))
    with scratch_dir():
        pass
    assert not stale.exists()


def test_sweep_removes_only_stale_prefixed_dirs(tmp_path: Path) -> None:
    """Fresh directories and directories without the prefix survive a sweep."""
    stale = tmp_path / f"{SCRATCH_PREFIX}old"
    fresh = tmp_path / f"{SCRATCH_PREFIX}new"
    other = tmp_path / "keep-old"
    for directory in (stale, fresh, other):
        directory.mkdir()
        (directory / "index").write_text("x")
    old = time.time() - STALE_AFTER_SECONDS - 60
    os.utime(stale, (old, old))
    os.utime(other, (old, old))
    sweep_stale(tmp_path)
    assert not stale.exists()
    assert fresh.exists()
    assert other.exists()


def test_sweep_ignores_missing_area(tmp_path: Path) -> None:
    """A missing area is not an error."""
    sweep_stale(tmp_path / "missing")
