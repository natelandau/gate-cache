"""Tests for the cached gate flow, status, and clear."""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from gate_cache import scratch
from gate_cache.gate import clear_cache, disabled_reason, gate_status, marker_max_age_days, run_gate
from gate_cache.markers import MISS_SUFFIX, marker_dir, miss_path
from gate_cache.runner import ChildResult
from gate_cache.snapshot import Snapshot
from tests.conftest import Counter, git

NAME = "pytest"


def markers(repo: Path) -> list[Path]:
    """Return the pass markers in the repo's marker directory."""
    directory = marker_dir(repo / ".git")
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir() if path.suffix != MISS_SUFFIX)


def misses(repo: Path) -> list[Path]:
    """Return the miss records in the repo's marker directory."""
    directory = marker_dir(repo / ".git")
    return sorted(directory.glob(f"*{MISS_SUFFIX}")) if directory.is_dir() else []


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


DISABLE_REASON = "caching disabled by GATE_CACHE_DISABLE"
CI_REASON = "caching disabled in CI (GATE_CACHE_DISABLE=0 keeps it on)"


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, None),
        ({"GATE_CACHE_DISABLE": ""}, None),
        ({"GATE_CACHE_DISABLE": "0"}, None),
        ({"GATE_CACHE_DISABLE": "1"}, DISABLE_REASON),
        ({"GATE_CACHE_DISABLE": "yes"}, DISABLE_REASON),
        ({"GATE_CACHE_DISABLE": "false"}, None),
        ({"GATE_CACHE_DISABLE": " False "}, None),
        ({"GATE_CACHE_DISABLE": " 0 "}, None),
        ({"GATE_CACHE_DISABLE": "  "}, None),
        ({"CI": "true"}, CI_REASON),
        ({"CI": "1"}, CI_REASON),
        ({"CI": "True"}, CI_REASON),
        ({"CI": "woodpecker"}, CI_REASON),
        ({"CI": ""}, None),
        ({"CI": "0"}, None),
        ({"CI": "false"}, None),
        ({"CI": " FALSE "}, None),
        ({"CI": "true", "GATE_CACHE_DISABLE": "0"}, None),
        ({"CI": "true", "GATE_CACHE_DISABLE": "false"}, None),
        ({"CI": "true", "GATE_CACHE_DISABLE": "  "}, CI_REASON),
        ({"CI": "true", "GATE_CACHE_DISABLE": ""}, CI_REASON),
        ({"CI": "true", "GATE_CACHE_DISABLE": "1"}, DISABLE_REASON),
        ({"CI": "false", "GATE_CACHE_DISABLE": "1"}, DISABLE_REASON),
    ],
)
def test_disabled_reason_values(environ: dict[str, str], expected: str | None) -> None:
    """Verify GATE_CACHE_DISABLE decides when set, and CI decides otherwise, by one rule."""
    assert disabled_reason(environ) == expected


def test_ci_env_always_runs_and_writes_nothing(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Verify a truthy CI bypasses the cache and names the override."""
    monkeypatch.setenv("CI", "true")
    run_gate(NAME, counter.argv())
    run_gate(NAME, counter.argv())
    assert counter.count == 2
    assert markers(git_repo) == []
    assert f"gate-cache: {CI_REASON}, running without cache" in capfd.readouterr().err


def test_disable_zero_keeps_caching_in_ci(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify GATE_CACHE_DISABLE=0 keeps caching on when CI is set."""
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GATE_CACHE_DISABLE", "0")
    run_gate(NAME, counter.argv())
    run_gate(NAME, counter.argv())
    assert counter.count == 1


def test_status_when_disabled_by_ci(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify status names CI as the reason caching is off."""
    monkeypatch.setenv("CI", "true")
    assert gate_status(NAME) == 1
    assert CI_REASON in capfd.readouterr().err


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
    git("update-index", "--skip-worktree", "a.txt", cwd=git_repo)
    assert gate_status(NAME) == 1
    out = capfd.readouterr().out
    assert "unknown: skip-worktree or assume-unchanged entry: a.txt" in out
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


def test_untracked_file_outside_cwd_is_part_of_the_key(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """From a subdirectory, an untracked file elsewhere is keyed by its content."""
    sub = _subdir(git_repo)
    (git_repo / "elsewhere.txt").write_text("x\n")
    monkeypatch.chdir(sub)
    run_gate(NAME, counter.argv())
    run_gate(NAME, counter.argv())
    assert counter.count == 1
    (git_repo / "elsewhere.txt").write_text("y\n")
    run_gate(NAME, counter.argv())
    assert counter.count == 2


def test_status_from_subdirectory_reports_unknown_reason(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Status from a subdirectory names a hidden entry elsewhere in the repo."""
    sub = _subdir(git_repo)
    git("update-index", "--skip-worktree", "a.txt", cwd=git_repo)
    monkeypatch.chdir(sub)
    assert gate_status(NAME) == 1
    assert "unknown: skip-worktree or assume-unchanged entry: a.txt" in capfd.readouterr().out


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
    """GIT_LITERAL_PATHSPECS cannot hide an untracked file outside the cwd from the key."""
    sub = _subdir(git_repo)
    (git_repo / "elsewhere.txt").write_text("x\n")
    monkeypatch.setenv("GIT_LITERAL_PATHSPECS", "1")
    monkeypatch.chdir(sub)
    run_gate(NAME, counter.argv())
    (git_repo / "elsewhere.txt").write_text("y\n")
    run_gate(NAME, counter.argv())
    assert counter.count == 2


def test_status_without_name_lists_passed_gates(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify status with no name lists every gate that passed on the current tree."""
    run_gate("pytest", counter.argv())
    run_gate("api-lint", counter.argv())
    capfd.readouterr()
    assert gate_status(None) == 0
    out = capfd.readouterr().out
    assert git("write-tree", cwd=git_repo) in out
    assert re.search(r"passed:\s+api-lint, pytest", out)
    assert "missed" not in out


def test_status_without_name_ignores_other_trees(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify gates that passed on an earlier tree are not listed."""
    run_gate("pytest", counter.argv())
    commit_change(git_repo, "changed")
    capfd.readouterr()
    assert gate_status(None) == 1
    out = capfd.readouterr().out
    assert "No gates match the current tree" in out
    assert "pytest" not in out


def test_status_without_name_and_no_markers(
    git_repo: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify an empty cache reports that no gates match."""
    assert gate_status(None) == 1
    assert "No gates match the current tree" in capfd.readouterr().out


def test_status_without_name_reports_unknown_tree(
    git_repo: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify an unknown tree reports the reason instead of a list."""
    git("update-index", "--skip-worktree", "a.txt", cwd=git_repo)
    assert gate_status(None) == 1
    out = capfd.readouterr().out
    assert "unknown: skip-worktree or assume-unchanged entry: a.txt" in out
    assert "No gates match" not in out


def test_status_without_name_when_disabled(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify status with no name honors GATE_CACHE_DISABLE."""
    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    assert gate_status(None) == 1
    assert "caching disabled" in capfd.readouterr().err


def test_status_without_name_when_git_dir_unknown(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify listing reports the missing git directory instead of an empty list."""
    monkeypatch.setattr("gate_cache.gate.git_common_dir", lambda: None)
    assert gate_status(None) == 1
    out = capfd.readouterr().out
    assert "could not locate git directory" in out
    assert "No gates match" not in out


def test_hook_in_worktree_subdirectory_skips_second_run(
    git_repo: Path, tmp_path: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify a hook-style run from a module directory of a linked worktree hits the cache."""
    (git_repo / "api").mkdir()
    (git_repo / "api" / "app.py").write_text("x = 1\n")
    git("add", "api/app.py", cwd=git_repo)
    git("commit", "-q", "-m", "add module", cwd=git_repo)
    worktree = tmp_path / "wt"
    git("worktree", "add", "-q", "--detach", str(worktree), cwd=git_repo)
    monkeypatch.setenv("GIT_DIR", git("rev-parse", "--absolute-git-dir", cwd=worktree))
    monkeypatch.chdir(worktree / "api")
    assert run_gate(NAME, counter.argv()) == 0
    assert run_gate(NAME, counter.argv()) == 0
    assert counter.count == 1


def test_derived_work_tree_is_not_passed_to_the_command(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify gate-cache leaves the wrapped command's environment unchanged."""
    worktree = tmp_path / "wt"
    git("worktree", "add", "-q", "--detach", str(worktree), cwd=git_repo)
    monkeypatch.setenv("GIT_DIR", git("rev-parse", "--absolute-git-dir", cwd=worktree))
    monkeypatch.chdir(worktree)
    seen = tmp_path / "seen.txt"
    probe = f"import os; open({str(seen)!r}, 'w').write(os.environ.get('GIT_WORK_TREE', 'unset'))"
    assert run_gate(NAME, [sys.executable, "-c", probe]) == 0
    assert seen.read_text() == "unset"


def test_failing_run_records_miss_and_status_lists_it(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a failed gate is listed as missed with its exit code next to the passed gates."""
    run_gate("pytest", counter.argv())
    run_gate("ruff", counter.argv(exit_code=3))
    capfd.readouterr()
    assert gate_status(None) == 0
    out = capfd.readouterr().out
    assert re.search(r"passed:\s+pytest", out)
    assert re.search(r"missed:\s+ruff \(exit code 3\)", out)


def test_status_lists_missed_gates_when_none_passed(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify missed gates are listed, and status exits 1, when nothing passed."""
    run_gate("ruff", counter.argv(exit_code=1))
    capfd.readouterr()
    assert gate_status(None) == 1
    out = capfd.readouterr().out
    assert re.search(r"missed:\s+ruff \(exit code 1\)", out)
    assert "passed" not in out
    assert "No gates match" not in out


def test_tree_changing_run_is_listed_as_missed(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a pass that changed the tree is reported as missed, not passed."""
    run_gate(NAME, counter.argv(touch=git_repo / "a.txt"))
    git("checkout", "a.txt", cwd=git_repo)
    capfd.readouterr()
    assert gate_status(None) == 1
    assert re.search(r"missed:\s+pytest \(files changed during the run\)", capfd.readouterr().out)


def test_pass_after_miss_removes_miss(git_repo: Path, counter: Counter) -> None:
    """Verify a later pass on the same tree deletes the miss record."""
    run_gate(NAME, counter.argv(exit_code=1))
    assert len(misses(git_repo)) == 1
    run_gate(NAME, counter.argv())
    assert misses(git_repo) == []
    assert len(markers(git_repo)) == 1


def test_interrupted_failure_records_no_miss(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify an interrupted run leaves no miss record, since it did not finish."""
    monkeypatch.setattr(
        "gate_cache.gate.run_child", lambda _argv: ChildResult(130, interrupted=True)
    )
    assert run_gate(NAME, ["true"]) == 130
    assert misses(git_repo) == []


def test_unwritable_miss_keeps_exit_code(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Verify a miss record that cannot be written only warns."""

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr("gate_cache.gate.write_miss", fail)
    assert run_gate(NAME, counter.argv(exit_code=4)) == 4
    assert (
        "warning: could not record miss: [Errno 30] Read-only file system" in capfd.readouterr().err
    )


def test_named_status_reports_last_failed_run(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify status --name shows how the last run on this tree failed."""
    run_gate(NAME, counter.argv(exit_code=2))
    capfd.readouterr()
    assert gate_status(NAME) == 1
    out = capfd.readouterr().out
    assert re.search(r"result:\s+miss", out)
    assert re.search(r"last run:\s+exit code 2", out)


def test_named_status_json_hit(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify status --name --json prints a parseable hit report on stdout."""
    run_gate(NAME, counter.argv())
    capfd.readouterr()
    assert gate_status(NAME, as_json=True) == 0
    data = json.loads(capfd.readouterr().out)
    assert data["enabled"] is True
    assert data["name"] == NAME
    assert data["tree"] == git("write-tree", cwd=git_repo)
    assert data["reason"] is None
    assert data["marker"] == str(markers(git_repo)[0])
    assert data["result"] == "hit"
    assert data["last_run"] is None


def test_named_status_json_miss_with_last_run(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify status --name --json reports the failed run's exit code and reason."""
    run_gate(NAME, counter.argv(exit_code=5))
    capfd.readouterr()
    assert gate_status(NAME, as_json=True) == 1
    data = json.loads(capfd.readouterr().out)
    assert data["result"] == "miss"
    assert data["last_run"]["exit_code"] == 5
    assert data["last_run"]["reason"] == "exit code 5"
    assert data["last_run"]["timestamp"]


def test_list_status_json(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify status --json lists passed and missed gates."""
    run_gate("pytest", counter.argv())
    run_gate("ruff", counter.argv(exit_code=1))
    capfd.readouterr()
    assert gate_status(None, as_json=True) == 0
    data = json.loads(capfd.readouterr().out)
    assert data["tree"] == git("write-tree", cwd=git_repo)
    assert data["reason"] is None
    assert data["passed"] == ["pytest"]
    assert [(m["name"], m["exit_code"]) for m in data["missed"]] == [("ruff", 1)]


def test_status_json_unknown_tree(git_repo: Path, capfd: pytest.CaptureFixture[str]) -> None:
    """Verify status --json gives the reason when the tree is unknown."""
    git("update-index", "--skip-worktree", "a.txt", cwd=git_repo)
    assert gate_status(None, as_json=True) == 1
    data = json.loads(capfd.readouterr().out)
    assert data["tree"] is None
    assert data["reason"] == "skip-worktree or assume-unchanged entry: a.txt"
    assert data["passed"] == []
    assert data["missed"] == []


def test_status_json_when_disabled(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify status --json reports disabled caching on stdout only."""
    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    assert gate_status(NAME, as_json=True) == 1
    captured = capfd.readouterr()
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data["enabled"] is False
    assert data["reason"] == "caching disabled by GATE_CACHE_DISABLE"


def test_skip_worktree_runs_uncached(git_repo: Path, counter: Counter) -> None:
    """A skip-worktree entry keeps every run uncached."""
    git("update-index", "--skip-worktree", "a.txt", cwd=git_repo)
    run_gate(NAME, counter.argv())
    run_gate(NAME, counter.argv())
    assert counter.count == 2
    assert markers(git_repo) == []


def test_pass_on_unstaged_edit_skips_after_commit(git_repo: Path, counter: Counter) -> None:
    """A pass on uncommitted edits skips once that content is committed."""
    (git_repo / "a.txt").write_text("edited\n")
    run_gate(NAME, counter.argv())
    git("commit", "-q", "-am", "edit", cwd=git_repo)
    run_gate(NAME, counter.argv())
    assert counter.count == 1


def test_pass_on_untracked_file_skips_after_commit(git_repo: Path, counter: Counter) -> None:
    """A pass with a new untracked file skips once that file is committed."""
    (git_repo / "new.txt").write_text("new\n")
    run_gate(NAME, counter.argv())
    git("add", "new.txt", cwd=git_repo)
    git("commit", "-q", "-m", "add", cwd=git_repo)
    run_gate(NAME, counter.argv())
    assert counter.count == 1


def test_further_edit_after_dirty_pass_reruns(git_repo: Path, counter: Counter) -> None:
    """Any further edit to dirty work changes the key."""
    (git_repo / "a.txt").write_text("first\n")
    run_gate(NAME, counter.argv())
    (git_repo / "a.txt").write_text("second\n")
    run_gate(NAME, counter.argv())
    assert counter.count == 2


def test_partial_commit_does_not_hit_full_working_copy_pass(
    git_repo: Path, counter: Counter
) -> None:
    """A commit holding part of the passed change runs again once the rest is set aside."""
    (git_repo / "a.txt").write_text("edited\n")
    (git_repo / "b.txt").write_text("b\n")
    run_gate(NAME, counter.argv())
    git("commit", "-q", "-am", "only a", cwd=git_repo)
    (git_repo / "b.txt").unlink()  # what a hook runner's stash leaves on disk
    run_gate(NAME, counter.argv())
    assert counter.count == 2


def test_command_that_edits_file_on_dirty_tree_records_nothing(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """A command that rewrites a file during a dirty-tree run gets no record."""
    (git_repo / "a.txt").write_text("edited\n")
    assert run_gate(NAME, counter.argv(touch=git_repo / "a.txt")) == 0
    assert markers(git_repo) == []
    assert "files changed during the run, not recording pass" in capfd.readouterr().err


def test_status_reports_tree_for_dirty_work(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Status reports a hit for a gate that passed on uncommitted work."""
    (git_repo / "a.txt").write_text("edited\n")
    run_gate(NAME, counter.argv())
    capfd.readouterr()
    assert gate_status(NAME) == 0
    assert re.search(r"result:\s+hit", capfd.readouterr().out)


def test_unusable_scratch_area_keeps_exit_code(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the temp area cannot be used, the command still runs and its exit code passes."""

    def denied() -> Path:
        msg = "denied"
        raise PermissionError(msg)

    monkeypatch.setattr(scratch, "runtime_area", denied)
    assert run_gate(NAME, counter.argv(exit_code=3)) == 3
    assert counter.count == 1
    assert markers(git_repo) == []


def test_status_json_when_disabled_keeps_report_keys(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify disabled caching still prints every key of the requested report."""
    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    assert gate_status(None, as_json=True) == 1
    data = json.loads(capfd.readouterr().out)
    assert data["passed"] == []
    assert data["missed"] == []
    assert gate_status(NAME, as_json=True) == 1
    data = json.loads(capfd.readouterr().out)
    assert data["name"] == NAME
    assert data["result"] == "miss"
    assert data["marker"] is None
    assert data["last_run"] is None


def test_status_lists_miss_without_reason_by_name_only(
    git_repo: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """A hand-written miss record with no reason lists the gate without a `(None)` suffix."""
    tree = git("write-tree", cwd=git_repo)
    common_dir = git_repo / ".git"
    path = miss_path(common_dir, tree, "ruff")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tree": tree, "name": "ruff"}), encoding="utf-8")
    assert gate_status(None) == 1
    out = capfd.readouterr().out
    assert re.search(r"missed:\s+ruff\n", out)
    assert "None" not in out
