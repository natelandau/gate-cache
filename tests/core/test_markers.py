"""Tests for marker files and the key contract."""

import json
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from gate_cache.durations import DURATIONS_DIRNAME, DURATIONS_NAME, durations_dir, durations_path
from gate_cache.gate import clear_cache
from gate_cache.markers import (
    MARKER_DIRNAME,
    MAX_RECORD_BYTES,
    clear_markers,
    marker_dir,
    marker_duration,
    marker_key,
    marker_path,
    miss_path,
    miss_record,
    missed_records,
    passed_names,
    prune_markers,
    select_markers,
    write_marker,
    write_miss,
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


def test_write_marker_records_duration(tmp_path: Path) -> None:
    """Verify a given duration is stored in seconds rounded to three decimals."""
    path = marker_path(tmp_path, TREE, "pytest")

    write_marker(path, tree=TREE, name="pytest", command=["pytest"], duration=1.23456)

    assert json.loads(path.read_text(encoding="utf-8"))["duration"] == 1.235


@pytest.mark.parametrize(
    ("content", "expected"), [('{"duration": 94.5}', 94.5), ('{"duration": 0}', 0.0)]
)
def test_marker_duration_reads_valid_value(tmp_path: Path, content: str, expected: float) -> None:
    """Verify a finite non-negative duration is read back as a float."""
    path = tmp_path / "marker"
    path.write_text(content, encoding="utf-8")

    result = marker_duration(path)

    assert result == expected
    assert isinstance(result, float)


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json",
        "[]",
        "{}",
        '{"duration": -1}',
        '{"duration": true}',
        '{"duration": "94"}',
        '{"duration": NaN}',
        '{"duration": Infinity}',
        '{"duration": 1' + "0" * 400 + "}",
        '{"duration": 1e300}',
        '{"duration": 2592001}',
        "[" * 100000,
    ],
)
def test_marker_duration_unusable(tmp_path: Path, content: str) -> None:
    """Verify unreadable, missing, or invalid durations read as None."""
    path = tmp_path / "marker"
    path.write_text(content, encoding="utf-8")

    assert marker_duration(path) is None


def test_marker_duration_missing_file(tmp_path: Path) -> None:
    """Verify a marker that does not exist has no duration."""
    assert marker_duration(tmp_path / "absent") is None


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


def test_prune_removes_only_old_records(tmp_path):
    """Verify pruning deletes old records and temp files, and keeps fresh and foreign files."""
    old = tmp_path / marker_key(TREE, "old")
    old_miss = tmp_path / f"{marker_key(TREE, 'old')}.miss"
    old_temp = tmp_path / ".tmp-abc"
    fresh = tmp_path / marker_key(TREE, "fresh")
    foreign = tmp_path / "notes.txt"
    stale = time.time() - 31 * 86400
    for path in (old, old_miss, old_temp, fresh, foreign):
        path.write_text("{}", encoding="utf-8")
    for path in (old, old_miss, old_temp, foreign):
        os.utime(path, (stale, stale))

    prune_markers(tmp_path)

    assert not old.exists()
    assert not old_miss.exists()
    assert not old_temp.exists()
    assert fresh.exists()
    assert foreign.exists()


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
    """Verify a marker that disappears after the listing but before its delete is not counted."""
    for name in ("a", "b"):
        write_marker(marker_path(tmp_path, TREE, name), tree=TREE, name=name, command=[name])
    vanishing = marker_key(TREE, "b")
    real_unlink = os.unlink

    def removed_first_by_another_run(path, *args, **kwargs):  # noqa: ANN202
        if Path(path).name == vanishing:
            real_unlink(path, *args, **kwargs)
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", removed_first_by_another_run)

    assert clear_markers(tmp_path) == 1
    assert not marker_dir(tmp_path).exists()


_VICTIM_NAMES = ("notes.txt", marker_key(TREE, "a"), durations_path(Path(), "a").name)


def _plant_victim(tmp_path: Path) -> Path:
    """Return a folder outside the repository holding old files, one with a marker's name."""
    victim = tmp_path / "victim"
    victim.mkdir()
    stale = time.time() - 40 * 86400
    for name in _VICTIM_NAMES:
        (victim / name).write_text("{}", encoding="utf-8")
        os.utime(victim / name, (stale, stale))
    return victim


@pytest.mark.parametrize(
    ("dirname", "operation"),
    [
        pytest.param(MARKER_DIRNAME, lambda common: clear_cache(common), id="clear-markers"),
        pytest.param(DURATIONS_DIRNAME, lambda common: clear_cache(common), id="clear-durations"),
        pytest.param(
            MARKER_DIRNAME,
            lambda common: clear_cache(common, select_markers(common, gate="a")),
            id="clear-one-gate",
        ),
        pytest.param(
            DURATIONS_DIRNAME,
            lambda common: clear_cache(common, select_markers(common, gate="a")),
            id="clear-one-gate-durations",
        ),
        pytest.param(
            MARKER_DIRNAME, lambda common: prune_markers(marker_dir(common)), id="prune-markers"
        ),
        pytest.param(
            DURATIONS_DIRNAME,
            lambda common: prune_markers(durations_dir(common), names=DURATIONS_NAME),
            id="prune-durations",
        ),
    ],
)
def test_symlinked_cache_dir_never_deletes_its_target(
    tmp_path: Path, dirname: str, operation: Callable[[Path], object]
) -> None:
    """Verify a planted symlink in the git dir cannot point a clear or prune at other files."""
    victim = _plant_victim(tmp_path)
    common = tmp_path / "common"
    common.mkdir()
    (common / dirname).symlink_to(victim)

    operation(common)

    assert sorted(p.name for p in victim.iterdir()) == sorted(_VICTIM_NAMES)


def test_select_markers_ignores_symlinked_marker_dir(tmp_path: Path) -> None:
    """Verify a dry run lists nothing in a symlinked marker folder, so it never counts its target."""
    victim = _plant_victim(tmp_path)
    marker_dir(tmp_path).symlink_to(victim)

    selection = select_markers(tmp_path)

    assert selection.passes == ()
    assert selection.misses == ()


def test_clear_removes_symlinked_marker_dir(tmp_path: Path) -> None:
    """Verify clearing removes the planted link itself, so the next run starts clean."""
    marker_dir(tmp_path).symlink_to(_plant_victim(tmp_path))

    assert clear_markers(tmp_path) == 0
    assert not marker_dir(tmp_path).is_symlink()


def test_write_marker_cleans_up_when_replace_fails(tmp_path, monkeypatch):
    """Verify a failed rename removes the temp file and surfaces the OSError."""
    path = marker_path(tmp_path, TREE, "pytest")

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError(18, "Cross-device link")

    monkeypatch.setattr(os, "replace", fail)

    with pytest.raises(OSError, match="Cross-device link"):
        write_marker(path, tree=TREE, name="pytest", command=["pytest"])
    assert list(path.parent.iterdir()) == []


def test_write_marker_never_writes_through_a_symlinked_directory(tmp_path: Path) -> None:
    """Verify a symlink planted at the marker directory cannot redirect a marker write."""
    victim = tmp_path / "victim"
    victim.mkdir()
    common = tmp_path / "common"
    common.mkdir()
    marker_dir(common).symlink_to(victim)

    with pytest.raises(OSError):  # noqa: PT011
        write_marker(marker_path(common, TREE, "pytest"), tree=TREE, name="pytest", command=["x"])

    assert list(victim.iterdir()) == []


OTHER_TREE = "aaff74984cccd156a469afa7d9ab10e4777beb24"


def test_passed_names_lists_gates_for_tree(tmp_path: Path) -> None:
    """Verify only gates recorded for the given tree are listed, sorted by name."""
    for tree, name in ((TREE, "pytest"), (TREE, "api-lint"), (OTHER_TREE, "ruff")):
        write_marker(marker_path(tmp_path, tree, name), tree=tree, name=name, command=["x"])
    assert passed_names(tmp_path, TREE, max_age_days=30) == ["api-lint", "pytest"]


def test_passed_names_skips_unreadable_and_mismatched_files(tmp_path: Path) -> None:
    """Verify files without matching JSON content are left out instead of failing."""
    write_marker(marker_path(tmp_path, TREE, "pytest"), tree=TREE, name="pytest", command=["x"])
    directory = marker_dir(tmp_path)
    (directory / marker_key(TREE, "touched")).write_text("")
    (directory / marker_key(TREE, "garbage")).write_text("not json")
    (directory / marker_key(TREE, "list")).write_text("[1, 2]")
    (directory / ("f" * 64)).write_text(json.dumps({"tree": TREE, "name": "forged"}))
    (directory / ".tmp-abc").write_text(json.dumps({"tree": TREE, "name": "partial"}))
    (directory / "subdir").mkdir()
    assert passed_names(tmp_path, TREE, max_age_days=30) == ["pytest"]


def test_passed_names_missing_dir_is_empty(tmp_path: Path) -> None:
    """Verify a repo with no marker directory lists no gates."""
    assert passed_names(tmp_path, TREE, max_age_days=30) == []


def test_missed_records_list_misses_without_a_pass(tmp_path: Path) -> None:
    """Verify miss records for the tree are listed by name, minus gates that also passed."""
    for name, code in (("ruff", 1), ("pytest", 2), ("ty", 3)):
        write_miss(
            miss_path(tmp_path, TREE, name),
            tree=TREE,
            name=name,
            command=["x"],
            exit_code=code,
            reason=f"exit code {code}",
        )
    write_miss(
        miss_path(tmp_path, OTHER_TREE, "other"),
        tree=OTHER_TREE,
        name="other",
        command=["x"],
        exit_code=1,
        reason="exit code 1",
    )
    write_marker(marker_path(tmp_path, TREE, "ty"), tree=TREE, name="ty", command=["x"])
    records = missed_records(tmp_path, TREE, max_age_days=30)
    assert [(r["name"], r["exit_code"]) for r in records] == [("pytest", 2), ("ruff", 1)]
    assert passed_names(tmp_path, TREE, max_age_days=30) == ["ty"]


def test_miss_record_is_not_a_marker(tmp_path: Path) -> None:
    """Verify a miss record never sits at the marker path, so it cannot cause a skip."""
    assert miss_path(tmp_path, TREE, "pytest") != marker_path(tmp_path, TREE, "pytest")
    assert miss_path(tmp_path, TREE, "pytest").name.startswith(marker_key(TREE, "pytest"))


def test_clear_markers_removes_misses_without_counting_them(tmp_path: Path) -> None:
    """Verify clear deletes miss records but reports only pass markers."""
    write_marker(marker_path(tmp_path, TREE, "a"), tree=TREE, name="a", command=["x"])
    write_miss(
        miss_path(tmp_path, TREE, "b"),
        tree=TREE,
        name="b",
        command=["x"],
        exit_code=1,
        reason="exit code 1",
    )
    assert clear_markers(tmp_path) == 1
    assert not marker_dir(tmp_path).exists()


def test_missed_records_skip_gates_with_contentless_marker(tmp_path: Path) -> None:
    """Verify a marker without JSON content still supersedes a miss, since it still skips."""
    write_miss(
        miss_path(tmp_path, TREE, "ruff"),
        tree=TREE,
        name="ruff",
        command=["x"],
        exit_code=1,
        reason="exit code 1",
    )
    marker_path(tmp_path, TREE, "ruff").touch()
    assert missed_records(tmp_path, TREE, max_age_days=30) == []


def test_miss_record_reads_one_gate(tmp_path: Path) -> None:
    """Verify one gate's miss record is read by name, and a missing one is None."""
    write_miss(
        miss_path(tmp_path, TREE, "ruff"),
        tree=TREE,
        name="ruff",
        command=["x"],
        exit_code=3,
        reason="exit code 3",
    )
    record = miss_record(tmp_path, TREE, "ruff")
    assert record is not None
    assert record["exit_code"] == 3
    assert miss_record(tmp_path, TREE, "pytest") is None
    assert miss_record(tmp_path, OTHER_TREE, "ruff") is None


def test_marker_duration_ignores_oversized_file(tmp_path: Path) -> None:
    """Verify a marker larger than any real record is not parsed."""
    path = tmp_path / "marker"
    path.write_text('{"duration": 5}' + " " * MAX_RECORD_BYTES, encoding="utf-8")

    assert marker_duration(path) is None


def test_marker_duration_ignores_fifo(tmp_path: Path) -> None:
    """Verify a FIFO at the marker path is not opened, which would block forever."""
    path = tmp_path / "marker"
    os.mkfifo(path)

    assert marker_duration(path) is None


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads files regardless of mode")
def test_marker_duration_unreadable_file(tmp_path: Path) -> None:
    """Verify a marker that cannot be read has no duration."""
    path = tmp_path / "marker"
    path.write_text('{"duration": 5}', encoding="utf-8")
    path.chmod(0o000)
    try:
        assert marker_duration(path) is None
    finally:
        path.chmod(0o644)


def test_marker_duration_reads_large_command(tmp_path: Path) -> None:
    """Verify a marker with a long command line, such as one listing many files, is read."""
    path = marker_path(tmp_path, TREE, "ruff")
    command = ["ruff", "check", *(f"src/pkg/module_{i:05}.py" for i in range(5000))]

    write_marker(path, tree=TREE, name="ruff", command=command, duration=2.0)

    assert marker_duration(path) == 2.0
