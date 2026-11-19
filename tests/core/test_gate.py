"""Tests for the cached gate flow, status, and clear."""

import contextlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Generator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from gate_cache import gate as gate_module
from gate_cache import scratch
from gate_cache.durations import DURATIONS_DIRNAME, durations_dir, durations_path, usual_duration
from gate_cache.gate import (
    USUAL_DURATION_NOTICE,
    clear_cache,
    disabled_reason,
    gate_status,
    marker_max_age_days,
    run_gate,
)
from gate_cache.gate_lock import HELD_ENV, LOCK_DIRNAME, GateLock, Holder, lock_path, read_holder
from gate_cache.markers import marker_dir, marker_path, miss_path, write_marker, write_miss
from gate_cache.runner import ChildResult
from gate_cache.snapshot import Snapshot, take_snapshot
from gate_cache.stats import junit
from gate_cache.wait_settings import FailedBehavior, WaitSettings
from tests.conftest import Counter, git, hide_common_dir, markers, misses, read_records

NAME = "pytest"


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
        f"gate-cache: {NAME} already passed on tree {tree[:12]}, skipping (saved <1s)\n"
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
    assert usual_duration(durations_path(git_repo / ".git", NAME)) is not None


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
    old_durations = durations_dir(git_repo / ".git") / "old.json"
    old_durations.parent.mkdir()
    old_durations.write_text("[1]")
    os.utime(old_durations, (stale, stale))
    run_gate(NAME, counter.argv())
    assert not old.exists()
    assert not old_durations.exists()
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
    assert "duration:" not in out
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
    assert clear_cache(confirmed=True) == 0
    assert "gate-cache: removed 1 marker\n" in capfd.readouterr().err
    assert not durations_dir(git_repo / ".git").exists()
    run_gate(NAME, counter.argv())
    assert counter.count == 2


def test_clear_keeps_markers_unless_confirmed(
    git_repo: Path,
    counter: Counter,
    answer: Callable[[str | None], None],
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Declining the prompt keeps every marker, and the warning names the marker directory."""
    run_gate(NAME, counter.argv())
    answer("no")
    assert clear_cache() == 1
    err = capfd.readouterr().err
    assert "permanently deletes every recorded pass" in err
    assert f"markers: {marker_dir(git_repo / '.git')}" in err
    assert len(markers(git_repo)) == 1


def test_clear_deletes_when_yes_typed(
    git_repo: Path, counter: Counter, answer: Callable[[str | None], None]
) -> None:
    """Typing yes at the prompt clears the markers."""
    run_gate(NAME, counter.argv())
    answer("yes")
    assert clear_cache() == 0
    assert markers(git_repo) == []


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
    assert clear_cache(confirmed=True) == 1
    assert "gate-cache: not a git repository" in capfd.readouterr().err


def test_clear_reports_os_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """A filesystem error while clearing is reported, not raised."""

    def fail(_common_dir: Path) -> int:
        raise OSError(16, "Resource busy")

    monkeypatch.setattr("gate_cache.gate.clear_markers", fail)
    assert clear_cache(confirmed=True) == 1
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

    def snapshot_then_fail(paths: Sequence[str] = ()) -> Snapshot:
        calls.append(1)
        if len(calls) > 1:
            msg = "boom"
            raise RuntimeError(msg)
        return real(paths=paths)

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
    hide_common_dir(monkeypatch)
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
    hide_common_dir(monkeypatch)
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
    assert clear_cache(confirmed=True) == 0
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
    assert isinstance(data["duration"], float)


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
    assert data["duration"] is None


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


def test_status_json_when_disabled_keeps_scope_keys(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a disabled scoped status --json carries the same keys as an enabled one."""
    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    assert gate_status(NAME, as_json=True, paths=["a.txt"]) == 1
    data = json.loads(capfd.readouterr().out)
    assert data["paths"] == ["a.txt"]
    assert data["full_tree"] is None


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
    assert "duration" not in data
    assert gate_status(NAME, as_json=True) == 1
    data = json.loads(capfd.readouterr().out)
    assert data["name"] == NAME
    assert data["result"] == "miss"
    assert data["marker"] is None
    assert data["last_run"] is None
    assert data["duration"] is None


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


def test_pass_records_duration(git_repo: Path, counter: Counter) -> None:
    """Verify a passing run stores its command's duration in the marker."""
    run_gate(NAME, counter.argv())

    (record,) = read_records(markers(git_repo))
    duration = record["duration"]
    assert isinstance(duration, float)
    assert duration >= 0


def test_skip_prints_recorded_duration(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a skip reports the duration stored in the marker."""
    run_gate(NAME, counter.argv())
    markers(git_repo)[0].write_text(json.dumps({"duration": 94}))
    capfd.readouterr()

    assert run_gate(NAME, counter.argv()) == 0

    assert counter.count == 1
    assert ", skipping (saved 1m 34s)\n" in capfd.readouterr().err


@pytest.mark.parametrize("content", ["{}", "not json"])
def test_skip_without_usable_duration_has_no_suffix(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str], content: str
) -> None:
    """Verify a marker without a usable duration still skips, without the suffix."""
    run_gate(NAME, counter.argv())
    markers(git_repo)[0].write_text(content)
    capfd.readouterr()

    assert run_gate(NAME, counter.argv()) == 0

    assert counter.count == 1
    assert capfd.readouterr().err.endswith(", skipping\n")


def _seed_durations(repo: Path, values: list[float]) -> Path:
    """Store recent run times for the NAME gate."""
    path = durations_path(repo / ".git", NAME)
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(values))
    return path


def test_run_announces_usual_duration(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a run prints the median of recent passes before the command runs."""
    _seed_durations(git_repo, [120, 130, 140])

    assert run_gate(NAME, counter.argv()) == 0

    notice = USUAL_DURATION_NOTICE.format(name=NAME, duration="2m 10s")
    assert f"gate-cache: {notice}\n" in capfd.readouterr().err


@pytest.mark.parametrize("seed", [None, [1.0], [0.2, 0.4]])
def test_run_without_slow_history_is_quiet(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str], seed: list[float] | None
) -> None:
    """Verify no estimate prints without history or at a median of 1s or less."""
    if seed is not None:
        _seed_durations(git_repo, seed)

    assert run_gate(NAME, counter.argv()) == 0

    assert f"running {NAME}" not in capfd.readouterr().err


def test_exit_zero_run_records_duration(git_repo: Path, counter: Counter) -> None:
    """Verify a passing run adds its run time to the gate's recent ones."""
    run_gate(NAME, counter.argv())

    assert usual_duration(durations_path(git_repo / ".git", NAME)) is not None


def test_failed_run_records_no_duration(git_repo: Path, counter: Counter) -> None:
    """Verify a failing run leaves the recent run times unchanged."""
    path = _seed_durations(git_repo, [120])

    run_gate(NAME, counter.argv(exit_code=5))

    assert json.loads(path.read_text()) == [120]


def test_unwritable_durations_keep_exit_code(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a durations store that cannot be written changes nothing about the run."""
    (git_repo / ".git" / DURATIONS_DIRNAME).write_text("a file, not a directory")

    assert run_gate(NAME, counter.argv()) == 0

    assert "warning" not in capfd.readouterr().err
    assert len(markers(git_repo)) == 1


def test_miss_record_has_no_duration(git_repo: Path, counter: Counter) -> None:
    """Verify a failed run's miss record carries no duration."""
    run_gate(NAME, counter.argv(exit_code=5))

    (record,) = read_records(misses(git_repo))
    assert "duration" not in record


def test_named_status_json_hit_without_duration(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a hit on a marker without a duration reports null."""
    run_gate(NAME, counter.argv())
    markers(git_repo)[0].write_text("{}")
    capfd.readouterr()

    assert gate_status(NAME, as_json=True) == 0

    data = json.loads(capfd.readouterr().out)
    assert data["result"] == "hit"
    assert data["duration"] is None


def test_named_status_text_hides_missing_duration(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a hit on a marker without a duration shows no duration row."""
    run_gate(NAME, counter.argv())
    markers(git_repo)[0].write_text("{}")
    capfd.readouterr()

    assert gate_status(NAME) == 0

    assert "duration:" not in capfd.readouterr().out


def test_named_status_text_shows_duration(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify the text report adds a duration row after the result row on a hit."""
    run_gate(NAME, counter.argv())
    markers(git_repo)[0].write_text(json.dumps({"duration": 94}))
    capfd.readouterr()

    assert gate_status(NAME) == 0

    out = capfd.readouterr().out
    assert re.search(r"result:\s+hit\n\s*duration:\s+1m 34s\n", out)


def _current_lock(name: str = NAME) -> tuple[Snapshot, Path]:
    """Return the snapshot of the working copy and its lock file for a gate name."""
    snap = take_snapshot()
    assert snap.key is not None
    assert snap.common_dir is not None
    return snap, lock_path(snap.common_dir, snap.key, name)


def _write_marker(snap: Snapshot, name: str = NAME) -> None:
    assert snap.key is not None
    assert snap.common_dir is not None
    write_marker(
        marker_path(snap.common_dir, snap.key, name), tree=snap.key, name=name, command=["x"]
    )


def _write_miss(snap: Snapshot, exit_code: int, name: str = NAME) -> None:
    assert snap.key is not None
    assert snap.common_dir is not None
    write_miss(
        miss_path(snap.common_dir, snap.key, name),
        tree=snap.key,
        name=name,
        command=["x"],
        exit_code=exit_code,
        reason=f"exit code {exit_code}",
    )


@dataclass
class WaitSpy:
    """What a test sees of the waiter's calls to GateLock.wait."""

    entered: threading.Event = field(default_factory=threading.Event)
    timeouts: list[float] = field(default_factory=list)


@pytest.fixture
def wait_spy(monkeypatch: pytest.MonkeyPatch) -> WaitSpy:
    """Record each wait for the lock and signal when the first one starts."""
    spy = WaitSpy()
    real = GateLock.wait

    def wait(path: Path, *, timeout: float) -> GateLock | None:
        spy.timeouts.append(timeout)
        spy.entered.set()
        return real(path, timeout=timeout)

    monkeypatch.setattr(GateLock, "wait", wait)
    return spy


@dataclass
class FakeClock:
    """A clock for the gate module whose monotonic time a test can move forward."""

    offset: float = 0.0
    real: bool = True

    def monotonic(self) -> float:
        """Return the offset, plus the real monotonic time unless `real` is off."""
        return (time.monotonic() if self.real else 0.0) + self.offset

    @staticmethod
    def time() -> float:
        """Return the real wall-clock time."""
        return time.time()


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Replace the clock the gate module reads, so tests can simulate long waits."""
    clock = FakeClock()
    monkeypatch.setattr("gate_cache.gate.time", clock)
    return clock


OtherRun = Callable[..., contextlib.AbstractContextManager[GateLock]]


@pytest.fixture
def other_run(wait_spy: WaitSpy) -> OtherRun:
    """Hold a lock as another run would, and finish that run once the waiter waits."""

    @contextlib.contextmanager
    def hold(
        path: Path, *, release: bool = True, then: Callable[[], None] | None = None
    ) -> Generator[GateLock]:
        lock = GateLock.try_acquire(path)
        assert lock is not None

        def finish() -> None:
            wait_spy.entered.wait(timeout=30)
            # Coarse filesystem clocks can stamp a file a few ms behind time.time().
            time.sleep(0.05)
            if then is not None:
                then()
            if release:
                lock.release()

        thread = threading.Thread(target=finish) if release or then is not None else None
        if thread is not None:
            thread.start()
        try:
            yield lock
        finally:
            wait_spy.entered.set()
            if thread is not None:
                thread.join()
            lock.release()

    return hold


def test_waits_then_skips_on_other_runs_pass(
    git_repo: Path, counter: Counter, other_run: OtherRun, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a run waits for a run with the same key, then skips on its pass."""
    snap, path = _current_lock()
    with other_run(path, then=lambda: _write_marker(snap)):
        assert run_gate(NAME, counter.argv()) == 0

    err = capfd.readouterr().err
    assert counter.count == 0
    assert f"{NAME} is running in " in err
    assert f"{NAME} already passed on {snap.label}, skipping" in err


def test_wait_message_names_holder_worktree(
    git_repo: Path, counter: Counter, other_run: OtherRun, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify the waiting line names the holder's worktree and its age."""
    snap, path = _current_lock()
    with other_run(path, then=lambda: _write_marker(snap)) as lock:
        lock.write_holder(Path("/elsewhere/wt"))
        run_gate(NAME, counter.argv())

    assert (
        f"gate-cache: {NAME} is running in /elsewhere/wt (started <1s ago), waiting\n"
        in capfd.readouterr().err
    )


def test_waits_then_runs_when_other_run_failed(
    git_repo: Path, counter: Counter, other_run: OtherRun
) -> None:
    """Verify the default behavior runs the command when the awaited run failed."""
    snap, path = _current_lock()
    with other_run(path, then=lambda: _write_miss(snap, 1)):
        assert run_gate(NAME, counter.argv()) == 0

    assert counter.count == 1
    assert len(markers(git_repo)) == 1


def test_report_returns_other_runs_exit_code(
    git_repo: Path, counter: Counter, other_run: OtherRun, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify report exits with the awaited run's exit code and does not run."""
    snap, path = _current_lock()
    with other_run(path, then=lambda: _write_miss(snap, 3)):
        code = run_gate(NAME, counter.argv(), wait=WaitSettings(failed="report"))

    assert code == 3
    assert counter.count == 0
    assert (
        f"{NAME} failed on {snap.label} in another process (exit 3), not running again"
        in capfd.readouterr().err
    )


def test_report_runs_after_files_changed_miss(
    git_repo: Path, counter: Counter, other_run: OtherRun
) -> None:
    """Verify a miss with exit code 0 makes even a reporting waiter run."""
    snap, path = _current_lock()
    with other_run(path, then=lambda: _write_miss(snap, 0)):
        assert run_gate(NAME, counter.argv(), wait=WaitSettings(failed="report")) == 0

    assert counter.count == 1


def test_report_ignores_miss_from_before_wait(
    git_repo: Path, counter: Counter, other_run: OtherRun
) -> None:
    """Verify a failure recorded before the wait started is not reported."""
    snap, path = _current_lock()
    _write_miss(snap, 1)
    miss = miss_path(git_repo / ".git", snap.key or "", NAME)
    stamp = time.time() - 10
    os.utime(miss, (stamp, stamp))
    with other_run(path):
        assert run_gate(NAME, counter.argv(), wait=WaitSettings(failed="report")) == 0

    assert counter.count == 1


@pytest.mark.parametrize("failed", ["rerun", "report"])
def test_runs_when_other_run_left_no_record(
    git_repo: Path, counter: Counter, other_run: OtherRun, failed: FailedBehavior
) -> None:
    """Verify an awaited run that recorded nothing makes the waiter run."""
    _, path = _current_lock()
    with other_run(path):
        assert run_gate(NAME, counter.argv(), wait=WaitSettings(failed=failed)) == 0

    assert counter.count == 1


def test_fresh_snapshot_after_wait(git_repo: Path, counter: Counter, other_run: OtherRun) -> None:
    """Verify the waiter decides on content after the wait, not on the key it waited on."""
    snap, path = _current_lock()

    def finish() -> None:
        _write_marker(snap)
        (git_repo / "a.txt").write_text("edited while waiting\n")

    with other_run(path, then=finish):
        assert run_gate(NAME, counter.argv()) == 0

    assert counter.count == 1
    assert len(markers(git_repo)) == 2


def test_fresh_snapshot_after_wait_checks_new_marker(
    git_repo: Path, counter: Counter, other_run: OtherRun, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a waiter whose content changed checks the new key's marker before running."""
    _, path = _current_lock()
    (git_repo / "a.txt").write_text("next\n")
    new_snap = take_snapshot()
    (git_repo / "a.txt").write_text("a\n")

    def finish() -> None:
        (git_repo / "a.txt").write_text("next\n")
        _write_marker(new_snap)

    with other_run(path, then=finish):
        assert run_gate(NAME, counter.argv()) == 0

    assert counter.count == 0
    assert f"already passed on {new_snap.label}" in capfd.readouterr().err


def test_fresh_snapshot_unknown_after_wait_runs_uncached(
    git_repo: Path, counter: Counter, other_run: OtherRun, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a tree that becomes unknown during the wait runs the command without cache."""
    _, path = _current_lock()

    def finish() -> None:
        git("update-index", "--skip-worktree", "a.txt", cwd=git_repo)

    with other_run(path, then=finish):
        assert run_gate(NAME, counter.argv()) == 0

    assert counter.count == 1
    assert "running without cache" in capfd.readouterr().err


def test_wait_timeout_runs_anyway(
    git_repo: Path, counter: Counter, other_run: OtherRun, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a wait that reaches the timeout runs the command without the lock."""
    _, path = _current_lock()
    with other_run(path, release=False):
        assert run_gate(NAME, counter.argv(), wait=WaitSettings(timeout=1)) == 0

    assert counter.count == 1
    assert (
        f"{NAME} still running in another process after 1s, running anyway"
        in capfd.readouterr().err
    )


def test_wait_timeout_runs_on_fresh_snapshot(
    git_repo: Path, counter: Counter, other_run: OtherRun
) -> None:
    """Verify a run that timed out records its pass on the content as it is after the wait."""
    _, path = _current_lock()

    def edit() -> None:
        (git_repo / "a.txt").write_text("edited while waiting\n")

    with other_run(path, release=False, then=edit):
        assert run_gate(NAME, counter.argv(), wait=WaitSettings(timeout=1)) == 0
        fresh, _ = _current_lock()

    assert counter.count == 1
    assert [p.name for p in markers(git_repo)] == [marker_path(Path(), fresh.key or "", NAME).name]


def test_waits_share_one_timeout(
    git_repo: Path, counter: Counter, fake_clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify a key change during a wait cannot restart the wait timeout."""
    fake_clock.real = False
    _, first = _current_lock()
    (git_repo / "a.txt").write_text("next\n")
    _, second = _current_lock()
    (git_repo / "a.txt").write_text("a\n")
    held_first = GateLock.try_acquire(first)
    held_second = GateLock.try_acquire(second)
    assert held_first is not None
    assert held_second is not None
    timeouts: list[float] = []

    def wait(path: Path, *, timeout: float) -> GateLock | None:
        timeouts.append(timeout)
        if path == first:
            fake_clock.offset += 4
            (git_repo / "a.txt").write_text("next\n")
            held_first.release()
            return GateLock.try_acquire(path)
        fake_clock.offset += timeout
        return None

    monkeypatch.setattr(GateLock, "wait", wait)
    try:
        assert run_gate(NAME, counter.argv(), wait=WaitSettings(timeout=10)) == 0
    finally:
        held_first.release()
        held_second.release()

    assert counter.count == 1
    assert timeouts == [10, 6]


def test_timeout_zero_runs_without_waiting(
    git_repo: Path,
    counter: Counter,
    other_run: OtherRun,
    wait_spy: WaitSpy,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Verify a zero timeout runs at once when the lock is taken."""
    _, path = _current_lock()
    with other_run(path, release=False):
        assert run_gate(NAME, counter.argv(), wait=WaitSettings(timeout=0)) == 0

    assert wait_spy.timeouts == []
    assert counter.count == 1
    assert "is running in" not in capfd.readouterr().err


def test_nested_call_skips_lock(
    git_repo: Path,
    counter: Counter,
    other_run: OtherRun,
    wait_spy: WaitSpy,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Verify a call nested in the lock holder's command runs without waiting on it."""
    _, path = _current_lock()
    with other_run(path, release=False):
        monkeypatch.setenv(HELD_ENV, path.name)
        assert run_gate(NAME, counter.argv(), wait=WaitSettings(timeout=2)) == 0

    assert wait_spy.timeouts == []
    assert counter.count == 1
    assert "is running in" not in capfd.readouterr().err


def test_lock_error_warns_and_runs(
    git_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a lock that cannot be created warns and the gate still runs and records."""
    snap, _ = _current_lock()
    assert snap.common_dir is not None
    (snap.common_dir / LOCK_DIRNAME).write_text("")

    assert run_gate(NAME, counter.argv()) == 0

    assert counter.count == 1
    assert f"warning: could not lock {NAME}: " in capfd.readouterr().err
    assert len(markers(git_repo)) == 1


def test_lock_error_while_waiting_warns_and_runs(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    stats_on: None,
    stats_dirs: tuple[Path, Path],
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Verify a lock error during the wait warns, keeps the wait time, and runs unlocked."""
    _, path = _current_lock()

    def fail(*_args: object, **_kwargs: object) -> GateLock | None:
        time.sleep(0.05)
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(GateLock, "wait", fail)
    held = GateLock.try_acquire(path)
    assert held is not None
    try:
        assert run_gate(NAME, counter.argv()) == 0
    finally:
        held.release()

    assert counter.count == 1
    assert f"warning: could not lock {NAME}: [Errno 13] Permission denied" in capfd.readouterr().err
    event = json.loads((stats_dirs[1] / "events.jsonl").read_text())
    assert event["outcome"] == "pass"
    assert event["waited"] > 0
    assert "wait_timed_out" not in event


def test_lock_free_but_marker_written_meanwhile_skips(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify a run that takes the lock re-checks the marker another run just wrote."""
    snap, _ = _current_lock()
    real = GateLock.try_acquire

    def finish_other_run_first(path: Path) -> GateLock | None:
        _write_marker(snap)
        return real(path)

    monkeypatch.setattr(GateLock, "try_acquire", finish_other_run_first)

    assert run_gate(NAME, counter.argv()) == 0
    assert counter.count == 0


def test_waited_recorded_in_stats(
    git_repo: Path,
    counter: Counter,
    other_run: OtherRun,
    wait_spy: WaitSpy,
    fake_clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    stats_on: None,
    stats_dirs: tuple[Path, Path],
) -> None:
    """Verify skips, timeouts, and reported failures after a wait record the wait."""
    snap, path = _current_lock()
    with other_run(path, then=lambda: _write_marker(snap)):
        run_gate(NAME, counter.argv())

    commit_change(git_repo, "b\n")
    _, path = _current_lock()

    def time_out(*_args: object, **_kwargs: object) -> GateLock | None:
        fake_clock.offset += 1000
        return None

    with monkeypatch.context() as patch, other_run(path, release=False):
        patch.setattr(GateLock, "wait", time_out)
        run_gate(NAME, counter.argv(), wait=WaitSettings(timeout=1))

    commit_change(git_repo, "c\n")
    snap, path = _current_lock()
    wait_spy.entered.clear()
    with other_run(path, then=lambda: _write_miss(snap, 2)):
        run_gate(NAME, counter.argv(), wait=WaitSettings(failed="report"))

    lines = (stats_dirs[1] / "events.jsonl").read_text().splitlines()
    skip, timed_out, reported = (json.loads(line) for line in lines)
    assert skip["outcome"] == "skip"
    assert skip["waited"] > 0
    assert "wait_timed_out" not in skip
    assert "reported" not in skip
    assert timed_out["outcome"] == "pass"
    assert timed_out["wait_timed_out"] is True
    assert timed_out["waited"] >= 1000
    assert timed_out["overhead"] < 1000
    assert reported["outcome"] == "fail"
    assert reported["duration"] is None
    assert reported["exit_code"] == 2
    assert reported["reason"] == "failed in another run, not rerun"
    assert reported["reported"] is True
    assert reported["waited"] > 0


def test_run_without_wait_records_no_waited(
    git_repo: Path, counter: Counter, stats_on: None, stats_dirs: tuple[Path, Path]
) -> None:
    """Verify a run that never waited leaves `waited` empty."""
    run_gate(NAME, counter.argv())

    event = json.loads((stats_dirs[1] / "events.jsonl").read_text())
    assert event["waited"] is None


def test_holder_publishes_held_env_to_child(
    git_repo: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify the command sees the lock it runs under in the nested-call variable."""
    _, path = _current_lock()
    code = f"import os; print(os.environ[{HELD_ENV!r}])"

    assert run_gate(NAME, [sys.executable, "-c", code]) == 0

    assert path.name in capfd.readouterr().out.strip().split(":")
    assert HELD_ENV not in os.environ
    lock = GateLock.try_acquire(path)
    assert lock is not None
    lock.release()


def test_new_holder_recorded_before_prerun_checks(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify a run arriving during the holder's pre-run checks sees the new holder."""
    snap, path = _current_lock()
    stale = GateLock.try_acquire(path)
    assert stale is not None
    stale.write_holder(Path("/stale/wt"))
    stale.release()
    seen: list[Holder | None] = []
    real = gate_module.marker_exists

    def marker_exists(marker: Path) -> bool:
        seen.append(read_holder(path))
        return real(marker)

    monkeypatch.setattr(gate_module, "marker_exists", marker_exists)
    assert run_gate(NAME, counter.argv()) == 0

    before_lock, during_checks = seen
    assert before_lock is not None
    assert before_lock.worktree == "/stale/wt"
    assert during_checks is not None
    assert during_checks.worktree == str(snap.root)
    assert during_checks.pid == os.getpid()


def _time_out(fake_clock: FakeClock, then: Callable[[], None] | None = None) -> Callable[..., None]:
    """Return a GateLock.wait stand-in that reaches the timeout at once."""

    def wait(*_args: object, **_kwargs: object) -> None:
        fake_clock.offset += 1000
        if then is not None:
            then()

    return wait


def test_timeout_then_unknown_tree_records_timed_out(
    git_repo: Path,
    counter: Counter,
    other_run: OtherRun,
    fake_clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    stats_on: None,
    stats_dirs: tuple[Path, Path],
) -> None:
    """Verify an uncached run after a timed-out wait records that the wait timed out."""
    _, path = _current_lock()

    def hide_tree() -> None:
        git("update-index", "--skip-worktree", "a.txt", cwd=git_repo)

    monkeypatch.setattr(GateLock, "wait", _time_out(fake_clock, then=hide_tree))
    with other_run(path, release=False):
        assert run_gate(NAME, counter.argv(), wait=WaitSettings(timeout=1)) == 0

    event = json.loads((stats_dirs[1] / "events.jsonl").read_text())
    assert event["outcome"] == "uncached"
    assert event["wait_timed_out"] is True
    assert event["waited"] >= 1000


def test_timeout_publishes_held_env_to_child(
    git_repo: Path,
    other_run: OtherRun,
    fake_clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Verify a run that timed out lists the hung lock, so a nested call does not wait again."""
    _, path = _current_lock()
    monkeypatch.setattr(GateLock, "wait", _time_out(fake_clock))
    code = f"import os; print(os.environ[{HELD_ENV!r}])"

    with other_run(path, release=False):
        assert run_gate(NAME, [sys.executable, "-c", code], wait=WaitSettings(timeout=1)) == 0

    assert path.name in capfd.readouterr().out.strip().split(":")
    assert HELD_ENV not in os.environ


def test_timeout_zero_publishes_held_env_to_child(
    git_repo: Path,
    other_run: OtherRun,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Verify a run that skipped a held lock lists it, so a nested call does not wait on it."""
    _, path = _current_lock()
    code = f"import os; print(os.environ[{HELD_ENV!r}])"

    with other_run(path, release=False):
        assert run_gate(NAME, [sys.executable, "-c", code], wait=WaitSettings(timeout=0)) == 0

    assert path.name in capfd.readouterr().out.strip().split(":")
    assert HELD_ENV not in os.environ


_REPORT_SCRIPT = """\
import sys
from pathlib import Path
cases = "".join(f'<testcase classname="c" name="t{i}" time="0.1"/>' for i in range(int(sys.argv[2])))
Path(sys.argv[1]).write_text(f"<testsuite>{cases}</testsuite>")
sys.exit(int(sys.argv[3]))
"""


def _report_command(report: Path, *, tests: int = 2, exit_code: int = 0) -> list[str]:
    """Return a command that writes a JUnit report with `tests` cases, then exits."""
    return [sys.executable, "-c", _REPORT_SCRIPT, str(report), str(tests), str(exit_code)]


def _events(state: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (state / "events.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("tests", [3, 0])
def test_junit_results_recorded(
    git_repo: Path, stats_on: None, stats_dirs: tuple[Path, Path], tests: int
) -> None:
    """Verify a fresh report, named relative to the cwd, counts its tests on the event.

    The tests are stored only when the report has any.
    """
    report = git_repo / "report.xml"
    assert run_gate(NAME, _report_command(report, tests=tests), junit=["report.xml"]) == 0

    (event,) = _events(stats_dirs[1])
    assert event["junit"] == tests
    assert "junit_truncated" not in event
    assert "junit_problem" not in event
    stored_file = stats_dirs[1] / "tests" / f"{event['id']}.json"
    if tests:
        stored = json.loads(stored_file.read_text())
        assert stored == [[f"c::t{i}", "pass", 0.1] for i in range(tests)]
    else:
        assert not stored_file.exists()


def test_junit_partial_read_records_the_problem(
    git_repo: Path, tmp_path: Path, stats_on: None, stats_dirs: tuple[Path, Path]
) -> None:
    """Verify a run that reads one report but misses another records the problem beside its count."""
    report = tmp_path / "report.xml"

    assert run_gate(NAME, _report_command(report), junit=[report, tmp_path / "gone.xml"]) == 0

    (event,) = _events(stats_dirs[1])
    assert event["junit"] == 2
    assert event["junit_problem"] == "missing"


def test_junit_stale_report_on_crash(
    git_repo: Path,
    counter: Counter,
    tmp_path: Path,
    stats_on: None,
    stats_dirs: tuple[Path, Path],
) -> None:
    """Verify a command that leaves an old report untouched keeps its exit code and records stale."""
    report = tmp_path / "report.xml"
    report.write_text('<testsuite><testcase name="old"/></testsuite>')

    assert run_gate(NAME, counter.argv(exit_code=3), junit=[report]) == 3

    (event,) = _events(stats_dirs[1])
    assert event["exit_code"] == 3
    assert event["junit"] == "stale"
    assert not (stats_dirs[1] / "tests").exists()


def test_junit_errors_never_change_exit_code(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stats_on: None,
    stats_dirs: tuple[Path, Path],
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Verify a failure while reading reports still records the run, with no junit field."""

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError

    monkeypatch.setattr(junit, "read_reports", fail)
    report = tmp_path / "report.xml"

    assert run_gate(NAME, _report_command(report, exit_code=4), junit=[report]) == 4

    (event,) = _events(stats_dirs[1])
    assert event["outcome"] == "fail"
    assert event["exit_code"] == 4
    assert event["junit"] is None
    assert capfd.readouterr().err == ""


def test_junit_ignored_without_stats(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stats_dirs: tuple[Path, Path],
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Verify --junit with stats off takes no snapshot, stores nothing, and prints nothing."""
    snapshots: list[object] = []
    monkeypatch.setattr(junit, "snapshot_reports", snapshots.append)
    report = tmp_path / "report.xml"

    assert run_gate(NAME, _report_command(report), junit=[report]) == 0

    assert snapshots == []
    assert not (stats_dirs[1] / "tests").exists()
    assert capfd.readouterr().err == ""


def test_skip_reads_no_report(
    git_repo: Path, tmp_path: Path, stats_on: None, stats_dirs: tuple[Path, Path]
) -> None:
    """Verify a skip stores no per-test file and leaves junit empty."""
    report = tmp_path / "report.xml"
    command = _report_command(report)
    run_gate(NAME, command, junit=[report])
    run_gate(NAME, command, junit=[report])

    ran, skipped = _events(stats_dirs[1])
    assert skipped["outcome"] == "skip"
    assert skipped["junit"] is None
    assert [p.stem for p in (stats_dirs[1] / "tests").iterdir()] == [ran["id"]]


def test_junit_recorded_for_uncached_run(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stats_on: None,
    stats_dirs: tuple[Path, Path],
) -> None:
    """Verify a run with caching off still records its tests."""
    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    report = tmp_path / "report.xml"

    assert run_gate(NAME, _report_command(report), junit=[report]) == 0

    (event,) = _events(stats_dirs[1])
    assert event["outcome"] == "uncached"
    assert event["junit"] == 2
    assert (stats_dirs[1] / "tests" / f"{event['id']}.json").exists()
