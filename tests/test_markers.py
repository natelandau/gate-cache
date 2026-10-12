"""Tests for marker files and the key contract."""

import json
import os
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from gate_cache.markers import (
    clear_markers,
    marker_dir,
    marker_key,
    marker_path,
    prune_markers,
    write_marker,
)

TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def test_key_contract_is_pinned():
    """Pin the key derivation shared with shell consumers.

    This is a public contract: changing it is a breaking change.
    """
    assert (
        marker_key(TREE, "pytest")
        == "782206e06519f9d0698636b4e04af444eb14aed369be938d7e5eff9702775dcf"
    )


def test_marker_path_layout():
    """Verify markers live under the gate-cache dir in the common git dir."""
    assert marker_dir(Path("/r/.git")) == Path("/r/.git/gate-cache")
    assert marker_path(Path("/r/.git"), TREE, "pytest") == Path("/r/.git/gate-cache") / marker_key(
        TREE, "pytest"
    )


def test_write_marker_writes_json(tmp_path):
    """Verify the marker holds the documented JSON fields."""
    path = marker_path(tmp_path, TREE, "pytest")

    write_marker(path, tree=TREE, name="pytest", command=["pytest", "-q"])

    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == {"tree", "name", "command", "timestamp"}
    assert data["command"] == ["pytest", "-q"]
    assert data["tree"] == TREE
    assert data["name"] == "pytest"
    assert isinstance(data["timestamp"], str)
    assert data["timestamp"]


def test_write_marker_leaves_no_temp_files(tmp_path):
    """Verify only the marker remains after a write."""
    path = marker_path(tmp_path, TREE, "pytest")

    write_marker(path, tree=TREE, name="pytest", command=["pytest"])

    assert list(path.parent.iterdir()) == [path]


def test_concurrent_writes_leave_one_valid_marker(tmp_path):
    """Verify parallel writers to one path leave a single valid marker."""
    path = marker_path(tmp_path, TREE, "pytest")

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(write_marker, path, tree=TREE, name="pytest", command=["pytest"])
            for _ in range(8)
        ]
        for future in futures:
            future.result()

    files = list(path.parent.iterdir())
    assert files == [path]
    assert json.loads(path.read_text(encoding="utf-8"))["name"] == "pytest"
    assert not [f for f in files if f.name.startswith(".tmp-")]


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_write_marker_raises_on_unwritable_dir(tmp_path):
    """Verify write failures surface as OSError."""
    parent = tmp_path / "gate-cache"
    parent.mkdir()
    parent.chmod(0o500)
    try:
        with pytest.raises(OSError):  # noqa: PT011
            write_marker(parent / "key", tree=TREE, name="pytest", command=["pytest"])
    finally:
        parent.chmod(0o700)


def test_prune_removes_only_old_files(tmp_path):
    """Verify pruning deletes markers older than the cutoff and keeps fresh ones."""
    old = tmp_path / "old"
    fresh = tmp_path / "fresh"
    old.write_text("{}", encoding="utf-8")
    fresh.write_text("{}", encoding="utf-8")
    stale = time.time() - 31 * 86400
    os.utime(old, (stale, stale))

    prune_markers(tmp_path)

    assert not old.exists()
    assert fresh.exists()


def test_prune_ignores_missing_dir(tmp_path):
    """Verify pruning a missing directory does not raise."""
    prune_markers(tmp_path / "missing")


def test_clear_markers_counts_and_removes(tmp_path):
    """Verify clearing deletes every marker and the directory."""
    for name in ("a", "b"):
        write_marker(marker_path(tmp_path, TREE, name), tree=TREE, name=name, command=[name])

    assert clear_markers(tmp_path) == 2
    assert not marker_dir(tmp_path).exists()
    assert clear_markers(tmp_path) == 0


def test_clear_markers_skips_temp_files_and_removes_subdirectories(tmp_path):
    """Verify temp files are not counted and stray subdirectories do not block clearing."""
    write_marker(marker_path(tmp_path, TREE, "a"), tree=TREE, name="a", command=["a"])
    directory = marker_dir(tmp_path)
    (directory / ".tmp-inflight").write_text("{}")
    (directory / "stray" / "nested").mkdir(parents=True)

    assert clear_markers(tmp_path) == 1
    assert not directory.exists()


def test_clear_markers_raises_when_directory_remains(tmp_path, monkeypatch):
    """Verify a directory that survives the fallback is reported, not claimed cleared."""
    write_marker(marker_path(tmp_path, TREE, "a"), tree=TREE, name="a", command=["a"])
    (marker_dir(tmp_path) / "stray").mkdir()
    monkeypatch.setattr("gate_cache.markers.shutil.rmtree", lambda *_a, **_k: None)

    with pytest.raises(OSError, match="could not remove"):
        clear_markers(tmp_path)


def test_clear_markers_does_not_count_vanished_files(tmp_path, monkeypatch):
    """Verify a marker that disappears before it is deleted is not counted."""
    for name in ("a", "b"):
        write_marker(marker_path(tmp_path, TREE, name), tree=TREE, name=name, command=[name])
    directory = marker_dir(tmp_path)
    real_iterdir = Path.iterdir

    def with_ghost(self: Path) -> Iterator[Path]:
        entries = list(real_iterdir(self))
        return iter([*entries, directory / "ghost"]) if self == directory else iter(entries)

    monkeypatch.setattr(Path, "iterdir", with_ghost)

    assert clear_markers(tmp_path) == 2
    assert not directory.exists()


def test_write_marker_cleans_up_when_replace_fails(tmp_path, monkeypatch):
    """Verify a failed rename removes the temp file and surfaces the OSError."""
    path = marker_path(tmp_path, TREE, "pytest")

    def fail(_self: Path, _target: Path) -> Path:
        raise OSError(18, "Cross-device link")

    monkeypatch.setattr(Path, "replace", fail)

    with pytest.raises(OSError, match="Cross-device link"):
        write_marker(path, tree=TREE, name="pytest", command=["pytest"])
    assert list(path.parent.iterdir()) == []
