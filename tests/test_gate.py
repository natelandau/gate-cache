"""Tests for the cached gate flow, status, and clear."""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from gate_cache.gate import cache_disabled, clear_cache, gate_status, marker_max_age_days, run_gate
from gate_cache.markers import marker_dir
from gate_cache.runner import ChildResult
from gate_cache.snapshot import Snapshot
from tests.conftest import Counter, git

NAME = "pytest"


def markers(repo: Path) -> list[Path]:
    """Return the files in the repo's marker directory."""
    directory = marker_dir(repo / ".git")
    return sorted(directory.iterdir()) if directory.is_dir() else []


def commit_change(repo: Path, content: str) -> None:
    """Commit new content for a.txt."""
    (repo / "a.txt").write_text(content)
    git("add", "a.txt", cwd=repo)
    git("commit", "-q", "-m", "change", cwd=repo)


def test_first_run_executes_and_second_skips(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """A passing run is recorded and the next run on the same tree skips."""
    assert run_gate(NAME, counter.argv()) == 0
    capfd.readouterr()
    assert run_gate(NAME, counter.argv()) == 0

    tree = git("write-tree", cwd=git_repo)
    assert counter.count == 1
    assert (
        f"gate-cache: {NAME} already passed on tree {tree[:12]}, skipping\n"
        in capfd.readouterr().err
    )


def test_tracked_change_reruns(git_repo: Path, counter: Counter) -> None:
    """Committed content changes produce a new tree."""
    run_gate(NAME, counter.argv())
    commit_change(git_repo, "b\n")
    run_gate(NAME, counter.argv())
    assert counter.count == 2


def test_added_file_reruns(git_repo: Path, counter: Counter) -> None:
    """A newly tracked file produces a new tree."""
    run_gate(NAME, counter.argv())
    (git_repo / "b.txt").write_text("b\n")
    git("add", "b.txt", cwd=git_repo)
    run_gate(NAME, counter.argv())
    assert counter.count == 2


def test_exec_bit_flip_reruns(git_repo: Path, counter: Counter) -> None:
    """A mode change produces a new tree."""
    run_gate(NAME, counter.argv())
    (git_repo / "a.txt").chmod(0o755)
    git("update-index", "--chmod=+x", "a.txt", cwd=git_repo)
    assert git("diff", cwd=git_repo) == ""
    run_gate(NAME, counter.argv())
    assert counter.count == 2


def test_returning_to_earlier_content_hits(git_repo: Path, counter: Counter) -> None:
    """Content seen before hits its old marker."""
    run_gate(NAME, counter.argv())
    commit_change(git_repo, "b\n")
    run_gate(NAME, counter.argv())
    commit_change(git_repo, "a\n")
    assert run_gate(NAME, counter.argv()) == 0
    assert counter.count == 2


def test_failing_command_passes_exit_code_and_writes_nothing(
    git_repo: Path, counter: Counter
) -> None:
    """A failure propagates and is never recorded."""
    assert run_gate(NAME, counter.argv(exit_code=1)) == 1
    assert markers(git_repo) == []
    run_gate(NAME, counter.argv(exit_code=1))
    assert counter.count == 2


def test_signal_killed_child_writes_nothing(git_repo: Path) -> None:
    """A signal death maps to 128 + signal and is never recorded."""
    code = "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"
    assert run_gate(NAME, [sys.executable, "-c", code]) == 143
    assert markers(git_repo) == []


def test_unstaged_change_runs_uncached(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Unstaged edits make the tree unknown."""
    (git_repo / "a.txt").write_text("dirty\n")
    run_gate(NAME, counter.argv())
    run_gate(NAME, counter.argv())
    assert counter.count == 2
    assert markers(git_repo) == []
    assert (
        "gate-cache: unstaged changes to tracked files, running without cache"
        in capfd.readouterr().err
    )


def test_untracked_file_runs_uncached(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Untracked files make the tree unknown."""
    (git_repo / "new.txt").write_text("new\n")
    run_gate(NAME, counter.argv())
    run_gate(NAME, counter.argv())
    assert counter.count == 2
    assert markers(git_repo) == []
    assert "running without cache" in capfd.readouterr().err


def test_ignored_file_does_not_block_caching(git_repo: Path, counter: Counter) -> None:
    """Ignored files are outside the key and do not block caching."""
    (git_repo / "ignored.txt").write_text("x\n")
    run_gate(NAME, counter.argv())
    run_gate(NAME, counter.argv())
    assert counter.count == 1


def test_staged_content_keyed_by_index(git_repo: Path, counter: Counter) -> None:
    """A pass on staged content hits once that content is committed."""
    (git_repo / "a.txt").write_text("staged\n")
    git("add", "a.txt", cwd=git_repo)
    run_gate(NAME, counter.argv())
    git("commit", "-q", "-m", "staged", cwd=git_repo)
    run_gate(NAME, counter.argv())
    assert counter.count == 1


def test_different_name_does_not_hit(git_repo: Path, counter: Counter) -> None:
    """Markers are per gate name."""
    run_gate("lint", counter.argv())
    run_gate("test", counter.argv())
    assert counter.count == 2


def test_linked_worktree_sees_main_markers(
    git_repo: Path, tmp_path: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Linked worktrees share markers through the git common dir."""
    run_gate(NAME, counter.argv())
    worktree = tmp_path / "wt"
    git("worktree", "add", "-q", "--detach", str(worktree), cwd=git_repo)
    monkeypatch.chdir(worktree)
    assert run_gate(NAME, counter.argv()) == 0
    assert counter.count == 1


def test_not_a_repo_runs_uncached(
    git_env: Path,
    tmp_path: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Outside a repo the command runs uncached."""
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(outside)
    assert run_gate(NAME, counter.argv(exit_code=3)) == 3
    assert run_gate(NAME, counter.argv()) == 0
    assert counter.count == 2
    assert "gate-cache: not a git repository, running without cache" in capfd.readouterr().err


def test_unmerged_index_runs_uncached(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """A conflicted merge makes the tree unknown."""
    git("checkout", "-q", "-b", "other", cwd=git_repo)
    commit_change(git_repo, "other\n")
    git("checkout", "-q", "main", cwd=git_repo)
    commit_change(git_repo, "main\n")
    with pytest.raises(subprocess.CalledProcessError):
        git("merge", "-q", "other", cwd=git_repo)
    run_gate(NAME, counter.argv())
    run_gate(NAME, counter.argv())
    assert counter.count == 2
    assert markers(git_repo) == []
    assert "gate-cache: unmerged index, running without cache" in capfd.readouterr().err


def test_disable_env_always_runs_and_writes_nothing(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """GATE_CACHE_DISABLE=1 bypasses the cache entirely."""
    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    run_gate(NAME, counter.argv())
    run_gate(NAME, counter.argv())
    assert counter.count == 2
    assert markers(git_repo) == []
    assert (
        "gate-cache: caching disabled by GATE_CACHE_DISABLE, running without cache"
        in capfd.readouterr().err
    )


def test_disable_zero_means_enabled(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GATE_CACHE_DISABLE=0 leaves caching on."""
    monkeypatch.setenv("GATE_CACHE_DISABLE", "0")
    run_gate(NAME, counter.argv())
    run_gate(NAME, counter.argv())
    assert counter.count == 1


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, False),
        ({"GATE_CACHE_DISABLE": ""}, False),
        ({"GATE_CACHE_DISABLE": "0"}, False),
        ({"GATE_CACHE_DISABLE": "1"}, True),
        ({"GATE_CACHE_DISABLE": "yes"}, True),
    ],
)
def test_cache_disabled_values(environ: dict[str, str], expected: bool) -> None:
    """Any non-empty value other than 0 disables caching."""
    assert cache_disabled(environ) is expected


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_unwritable_marker_dir_keeps_exit_code(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """A write failure warns and keeps the command's exit code."""
    directory = marker_dir(git_repo / ".git")
    directory.mkdir()
    directory.chmod(0o500)
    try:
        assert run_gate(NAME, counter.argv()) == 0
    finally:
        directory.chmod(0o700)
    assert "gate-cache: warning: could not record pass: " in capfd.readouterr().err
    assert markers(git_repo) == []


def test_command_that_edits_tracked_file_records_nothing(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """A command that rewrites tracked files gets no record."""
    assert run_gate(NAME, counter.argv(touch=git_repo / "a.txt")) == 0
    assert markers(git_repo) == []
    assert (
        "gate-cache: files changed during the run, not recording pass\n" in capfd.readouterr().err
    )


def test_command_that_creates_untracked_file_records_nothing(
    git_repo: Path, counter: Counter
) -> None:
    """A command that leaves untracked files behind gets no record."""
    assert run_gate(NAME, counter.argv(touch=git_repo / "new.txt")) == 0
    assert markers(git_repo) == []


def test_missing_command_writes_nothing(git_repo: Path) -> None:
    """A missing command exits 127 and is never recorded."""
    assert run_gate(NAME, ["definitely-not-a-command-xyz"]) == 127
    assert markers(git_repo) == []


def test_name_with_brackets_prints_verbatim(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Rich markup in names is printed literally."""
    run_gate("unit [fast]", counter.argv())
    run_gate("unit [fast]", counter.argv())
    assert "gate-cache: unit [fast] already passed on tree" in capfd.readouterr().err


def test_prune_runs_after_write(git_repo: Path, counter: Counter) -> None:
    """Old markers are pruned after a successful write."""
    directory = marker_dir(git_repo / ".git")
    directory.mkdir()
    old = directory / "old"
    old.write_text("{}")
    stale = time.time() - 31 * 86400
    os.utime(old, (stale, stale))
    run_gate(NAME, counter.argv())
    assert not old.exists()
    assert len(markers(git_repo)) == 1


def _plant_marker(repo: Path, name: str, age_days: float) -> Path:
    """Create a marker file whose mtime is age_days in the past."""
    directory = marker_dir(repo / ".git")
    directory.mkdir(exist_ok=True)
    path = directory / name
    path.write_text("{}")
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


def test_max_age_env_shortens_pruning(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify GATE_CACHE_MAX_AGE_DAYS prunes markers younger than the 30-day default."""
    monkeypatch.setenv("GATE_CACHE_MAX_AGE_DAYS", "7")
    older = _plant_marker(git_repo, "older", age_days=8)
    newer = _plant_marker(git_repo, "newer", age_days=6)
    run_gate(NAME, counter.argv())
    assert not older.exists()
    assert newer.exists()


def test_max_age_env_lengthens_pruning(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify GATE_CACHE_MAX_AGE_DAYS keeps markers older than the 30-day default."""
    monkeypatch.setenv("GATE_CACHE_MAX_AGE_DAYS", "90")
    kept = _plant_marker(git_repo, "kept", age_days=60)
    run_gate(NAME, counter.argv())
    assert kept.exists()


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 30), ("", 30), ("7", 7), (" 14 ", 14), ("365", 365)],
)
def test_marker_max_age_days_valid(value: str | None, expected: int) -> None:
    """Verify valid or unset values give the configured or default age."""
    environ = {} if value is None else {"GATE_CACHE_MAX_AGE_DAYS": value}
    assert marker_max_age_days(environ) == expected


@pytest.mark.parametrize("value", ["0", "-3", "seven", "1.5"])
def test_marker_max_age_days_invalid_warns_and_uses_default(
    value: str, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify an invalid value warns and falls back to 30 days instead of failing."""
    assert marker_max_age_days({"GATE_CACHE_MAX_AGE_DAYS": value}) == 30
    err = capfd.readouterr().err
    assert "GATE_CACHE_MAX_AGE_DAYS" in err
    assert "using 30" in err


def test_invalid_max_age_keeps_exit_code(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify an invalid max age never changes the command's exit code or blocks recording."""
    monkeypatch.setenv("GATE_CACHE_MAX_AGE_DAYS", "nope")
    assert run_gate(NAME, counter.argv()) == 0
    assert len(markers(git_repo)) == 1


def test_status_hit_and_miss(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Status reports a miss before a pass and a hit after."""
    assert gate_status(NAME) == 1
    out = capfd.readouterr().out
    assert re.search(r"result:\s+miss", out)
    assert git("write-tree", cwd=git_repo) in out

    run_gate(NAME, counter.argv())
    capfd.readouterr()
    assert gate_status(NAME) == 0
    out = capfd.readouterr().out
    assert re.search(r"result:\s+hit", out)
    assert str(markers(git_repo)[0]) in out
    assert counter.count == 1


def test_status_reports_unknown_reason(git_repo: Path, capfd: pytest.CaptureFixture[str]) -> None:
    """Status explains why the tree is unknown."""
    (git_repo / "new.txt").write_text("new\n")
    assert gate_status(NAME) == 1
    out = capfd.readouterr().out
    assert "unknown: untracked file: new.txt" in out
    assert re.search(r"result:\s+miss", out)


def test_status_when_disabled(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Status reports that caching is disabled."""
    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    assert gate_status(NAME) == 1
    assert "caching disabled by GATE_CACHE_DISABLE" in capfd.readouterr().err


def test_clear_removes_markers(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Clear deletes markers so the next run executes."""
    run_gate(NAME, counter.argv())
    assert clear_cache() == 0
    assert "gate-cache: removed 1 marker\n" in capfd.readouterr().err
    run_gate(NAME, counter.argv())
    assert counter.count == 2


def test_clear_outside_repo_fails(
    git_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Clear outside a repo is an error."""
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(outside)
    assert clear_cache() == 1
    assert "gate-cache: not a git repository" in capfd.readouterr().err


def test_clear_reports_os_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """A filesystem error while clearing is reported, not raised."""

    def fail(_common_dir: Path) -> int:
        raise OSError(16, "Resource busy")

    monkeypatch.setattr("gate_cache.gate.clear_markers", fail)
    assert clear_cache() == 1
    assert "gate-cache: could not clear markers: " in capfd.readouterr().err


def test_interrupted_pass_writes_nothing(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interrupted run is never recorded, even when the child exits 0."""
    monkeypatch.setattr("gate_cache.gate.run_child", lambda _argv: ChildResult(0, interrupted=True))
    assert run_gate(NAME, counter.argv()) == 0
    assert markers(git_repo) == []


def _subdir(repo: Path) -> Path:
    """Create and track a subdirectory so the tree is otherwise clean."""
    sub = repo / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("c\n")
    git("add", "sub/c.txt", cwd=repo)
    git("commit", "-q", "-m", "sub", cwd=repo)
    return sub


def test_untracked_file_outside_cwd_runs_uncached(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """From a subdirectory, an untracked file elsewhere still blocks caching."""
    sub = _subdir(git_repo)
    (git_repo / "elsewhere.txt").write_text("x\n")
    monkeypatch.chdir(sub)
    run_gate(NAME, counter.argv())
    run_gate(NAME, counter.argv())
    assert counter.count == 2
    assert markers(git_repo) == []
    assert (
        "gate-cache: untracked file: elsewhere.txt, running without cache" in capfd.readouterr().err
    )


def test_status_from_subdirectory_reports_untracked_file(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Status from a subdirectory names an untracked file elsewhere in the repo."""
    sub = _subdir(git_repo)
    (git_repo / "elsewhere.txt").write_text("x\n")
    monkeypatch.chdir(sub)
    assert gate_status(NAME) == 1
    assert "unknown: untracked file: elsewhere.txt" in capfd.readouterr().out


def test_unexpected_error_after_pass_keeps_exit_code(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """An unexpected error while recording a pass warns and keeps the exit code."""
    from gate_cache import gate

    real = gate.take_snapshot
    calls: list[int] = []

    def snapshot_then_fail() -> Snapshot:
        calls.append(1)
        if len(calls) > 1:
            msg = "boom"
            raise RuntimeError(msg)
        return real()

    monkeypatch.setattr("gate_cache.gate.take_snapshot", snapshot_then_fail)
    assert run_gate(NAME, counter.argv()) == 0
    assert counter.count == 1
    assert markers(git_repo) == []
    assert "gate-cache: warning: could not record pass: boom" in capfd.readouterr().err


def test_no_common_dir_runs_uncached(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """A known tree without a locatable git directory runs uncached and records nothing."""
    monkeypatch.setattr("gate_cache.gate.git_common_dir", lambda: None)
    assert run_gate(NAME, counter.argv(exit_code=4)) == 4
    assert run_gate(NAME, counter.argv()) == 0
    assert counter.count == 2
    assert markers(git_repo) == []
    assert (
        "gate-cache: could not locate git directory, running without cache"
        in capfd.readouterr().err
    )


def test_status_reports_missing_common_dir(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Status explains a miss caused by an unlocatable git directory."""
    monkeypatch.setattr("gate_cache.gate.git_common_dir", lambda: None)
    assert gate_status(NAME) == 1
    out = capfd.readouterr().out
    assert git("write-tree", cwd=git_repo) in out
    assert "none: could not locate git directory" in out
    assert re.search(r"result:\s+miss", out)


def test_marker_check_error_is_a_miss(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An OSError while checking for a marker counts as a miss, so the command runs."""
    run_gate(NAME, counter.argv())

    real_exists = Path.exists

    def fail_for_markers(self: Path, **kwargs: bool) -> bool:
        if self.parent.name == "gate-cache":
            raise PermissionError(13, "Permission denied")
        return real_exists(self, **kwargs)

    monkeypatch.setattr(Path, "exists", fail_for_markers)
    assert run_gate(NAME, counter.argv()) == 0
    assert counter.count == 2


@pytest.mark.parametrize(("count", "expected"), [(0, "0 markers"), (2, "2 markers")])
def test_clear_reports_plural_count(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    count: int,
    expected: str,
) -> None:
    """Clear uses the plural for any count other than one."""
    monkeypatch.setattr("gate_cache.gate.clear_markers", lambda _common_dir: count)
    assert clear_cache() == 0
    assert f"gate-cache: removed {expected}\n" in capfd.readouterr().err


def test_disable_env_makes_no_git_calls(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With caching disabled the command runs without touching git."""

    def no_git(*_args: object, **_kwargs: object) -> None:
        msg = "git must not be called"
        raise AssertionError(msg)

    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    monkeypatch.setattr("gate_cache.snapshot.run_git", no_git)
    monkeypatch.setattr("gate_cache.gate.take_snapshot", no_git)
    monkeypatch.setattr("gate_cache.gate.git_common_dir", no_git)
    assert run_gate(NAME, counter.argv(exit_code=3)) == 3
    assert counter.count == 1


def test_literal_pathspecs_do_not_hide_untracked_files(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GIT_LITERAL_PATHSPECS cannot hide an untracked file outside the cwd."""
    sub = _subdir(git_repo)
    (git_repo / "elsewhere.txt").write_text("x\n")
    monkeypatch.setenv("GIT_LITERAL_PATHSPECS", "1")
    monkeypatch.chdir(sub)
    run_gate(NAME, counter.argv())
    run_gate(NAME, counter.argv())
    assert counter.count == 2
    assert markers(git_repo) == []
