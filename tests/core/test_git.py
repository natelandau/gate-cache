"""Tests for the git subprocess runner."""

import os
from pathlib import Path

import pytest

from gate_cache.git import GitFailedError, GitNotFoundError, run_git
from tests.conftest import git


def test_run_git_returns_output_without_trailing_newline(git_repo: Path) -> None:
    """Stdout is decoded with its trailing newline removed."""
    result = run_git("rev-parse", "--show-toplevel", cwd=git_repo)
    assert result.returncode == 0
    assert result.stdout == str(git_repo.resolve())


def test_run_git_keeps_carriage_returns_in_paths(git_repo: Path) -> None:
    """A carriage return in a file name survives decoding."""
    (git_repo / "a\rb.txt").write_text("x\n")
    git("add", "-A", cwd=git_repo)
    names = run_git("ls-files", "-z", cwd=git_repo).stdout.split("\0")
    assert "a\rb.txt" in names


def test_run_git_failure_raises_under_check(git_repo: Path) -> None:
    """A non-zero exit raises when check is on and is returned when it is off."""
    with pytest.raises(GitFailedError, match="exit code"):
        run_git("rev-parse", "--verify", "no-such-ref", cwd=git_repo)
    result = run_git("rev-parse", "--verify", "no-such-ref", cwd=git_repo, check=False)
    assert result.returncode != 0
    assert result.stderr


def test_run_git_missing_cwd_is_a_failure(tmp_path: Path) -> None:
    """A cwd that is not a directory fails instead of reporting git as missing."""
    with pytest.raises(GitFailedError, match="not a directory"):
        run_git("status", cwd=tmp_path / "missing")


def test_run_git_missing_executable(tmp_path: Path) -> None:
    """A PATH without git raises GitNotFoundError."""
    with pytest.raises(GitNotFoundError):
        run_git("status", cwd=tmp_path, env={**os.environ, "PATH": str(tmp_path)})


def test_run_git_does_not_read_stdin(git_repo: Path) -> None:
    """Git gets an empty stdin, so a command that reads it never blocks."""
    result = run_git("hash-object", "--stdin", cwd=git_repo)
    assert result.stdout == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def test_run_git_rejects_undecodable_output(git_repo: Path) -> None:
    """Output that is not UTF-8 raises UnicodeDecodeError."""
    (git_repo / "bad.txt").write_bytes(b"\xff\xfe\n")
    git("add", "bad.txt", cwd=git_repo)
    with pytest.raises(UnicodeDecodeError):
        run_git("show", ":bad.txt", cwd=git_repo)
