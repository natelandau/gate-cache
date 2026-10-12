"""Tests for snapshot detection."""

import stat
import subprocess
from pathlib import Path

import pytest

from gate_cache.snapshot import git_common_dir, take_snapshot
from tests.conftest import git


def test_clean_repo_tree_equals_head_tree(git_repo: Path) -> None:
    """Clean repo tree equals head tree."""
    snap = take_snapshot()
    assert snap.tree == git("rev-parse", "HEAD^{tree}", cwd=git_repo)
    assert snap.reason is None
    assert snap.known is True


def test_content_change_changes_tree(git_repo: Path) -> None:
    """Content change changes tree."""
    before = take_snapshot().tree
    (git_repo / "a.txt").write_text("changed\n")
    git("add", "a.txt", cwd=git_repo)
    after = take_snapshot()
    assert after.known
    assert after.tree != before


def test_added_file_changes_tree(git_repo: Path) -> None:
    """Added file changes tree."""
    before = take_snapshot().tree
    (git_repo / "b.txt").write_text("b\n")
    git("add", "b.txt", cwd=git_repo)
    after = take_snapshot()
    assert after.known
    assert after.tree != before


def test_exec_bit_flip_changes_tree(git_repo: Path) -> None:
    """Exec bit flip changes tree."""
    before = take_snapshot().tree
    path = git_repo / "a.txt"
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    git("add", "a.txt", cwd=git_repo)
    after = take_snapshot()
    assert after.known
    assert after.tree != before


def test_staged_uncommitted_keys_by_index(git_repo: Path) -> None:
    """Staged uncommitted keys by index."""
    (git_repo / "a.txt").write_text("staged\n")
    git("add", "a.txt", cwd=git_repo)
    snap = take_snapshot()
    assert snap.tree == git("write-tree", cwd=git_repo)
    assert snap.tree != git("rev-parse", "HEAD^{tree}", cwd=git_repo)


def test_unstaged_change_is_unknown(git_repo: Path) -> None:
    """Unstaged change is unknown."""
    (git_repo / "a.txt").write_text("unstaged\n")
    snap = take_snapshot()
    assert snap.known is False
    assert snap.reason is not None
    assert "unstaged" in snap.reason


def test_untracked_file_is_unknown(git_repo: Path) -> None:
    """Untracked file is unknown."""
    (git_repo / "new.py").write_text("x = 1\n")
    snap = take_snapshot()
    assert snap.known is False
    assert snap.reason == "untracked file: new.py"


def test_ignored_file_does_not_block(git_repo: Path) -> None:
    """Ignored file does not block."""
    (git_repo / "ignored.txt").write_text("ignored\n")
    assert take_snapshot().known is True


def test_not_a_repo_is_unknown(
    tmp_path: Path, git_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not a repo is unknown."""
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    snap = take_snapshot()
    assert snap.known is False
    assert snap.reason == "not a git repository"


def test_unmerged_index_is_unknown(git_repo: Path) -> None:
    """Unmerged index is unknown."""
    git("checkout", "-q", "-b", "other", cwd=git_repo)
    (git_repo / "a.txt").write_text("other\n")
    git("commit", "-q", "-am", "other", cwd=git_repo)
    git("checkout", "-q", "main", cwd=git_repo)
    (git_repo / "a.txt").write_text("main\n")
    git("commit", "-q", "-am", "main", cwd=git_repo)
    merge = subprocess.run(
        ["git", "merge", "other"],  # noqa: S607
        cwd=git_repo,
        capture_output=True,
        check=False,
    )
    assert merge.returncode != 0
    snap = take_snapshot()
    assert snap.known is False
    assert snap.reason == "unmerged index"


def test_git_missing_is_unknown(
    tmp_path: Path, git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Git missing is unknown."""
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    snap = take_snapshot()
    assert snap.known is False
    assert snap.reason == "git not found"


def test_subdirectory_gives_same_tree(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Subdirectory gives same tree."""
    sub = git_repo / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("c\n")
    git("add", "sub/c.txt", cwd=git_repo)
    root_tree = take_snapshot().tree
    monkeypatch.chdir(sub)
    assert take_snapshot().tree == root_tree


def test_repo_without_commits_is_known(
    tmp_path: Path, git_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repo without commits is known."""
    repo = tmp_path / "fresh"
    repo.mkdir()
    git("init", "-q", cwd=repo)
    (repo / "f.txt").write_text("f\n")
    git("add", "f.txt", cwd=repo)
    monkeypatch.chdir(repo)
    assert take_snapshot().known is True


def test_linked_worktree_shares_common_dir(git_repo: Path) -> None:
    """Linked worktree shares common dir."""
    wt = git_repo.parent / "wt"
    git("worktree", "add", "-q", str(wt), cwd=git_repo)
    common = git_common_dir(wt)
    assert common is not None
    assert common == git_common_dir(git_repo)
    assert common.is_absolute()
    assert take_snapshot(wt).tree == take_snapshot(git_repo).tree
    assert take_snapshot(wt).known


def test_git_common_dir_outside_repo_is_none(
    tmp_path: Path, git_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Git common dir outside repo is none."""
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    assert git_common_dir(plain) is None


def _raise_undecodable(*args: str, **kwargs: object) -> None:
    error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
    raise error


def test_undecodable_git_output_is_unknown(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Undecodable git output resolves to an unknown snapshot."""
    monkeypatch.setattr("gate_cache.snapshot.run_git", _raise_undecodable)
    snap = take_snapshot()
    assert snap.known is False
    assert snap.reason == "could not inspect git state"
    assert git_common_dir() is None


def test_untracked_file_outside_cwd_is_unknown(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An untracked file anywhere in the repo makes the tree unknown from a subdirectory."""
    sub = git_repo / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("c\n")
    git("add", "sub/c.txt", cwd=git_repo)
    (git_repo / "elsewhere.txt").write_text("x\n")
    monkeypatch.chdir(sub)
    snap = take_snapshot()
    assert snap.known is False
    assert snap.reason == "untracked file: elsewhere.txt"


def test_unmerged_file_outside_cwd_is_unknown(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A conflict anywhere in the repo makes the tree unknown from a subdirectory."""
    sub = git_repo / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("c\n")
    git("add", "sub/c.txt", cwd=git_repo)
    git("commit", "-q", "-m", "sub", cwd=git_repo)
    git("checkout", "-q", "-b", "other", cwd=git_repo)
    (git_repo / "a.txt").write_text("other\n")
    git("commit", "-q", "-am", "other", cwd=git_repo)
    git("checkout", "-q", "main", cwd=git_repo)
    (git_repo / "a.txt").write_text("main\n")
    git("commit", "-q", "-am", "main", cwd=git_repo)
    with pytest.raises(subprocess.CalledProcessError):
        git("merge", "-q", "other", cwd=git_repo)
    monkeypatch.chdir(sub)
    assert take_snapshot().reason == "unmerged index"


def test_git_common_dir_from_subdirectory_is_absolute(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The common dir is the absolute .git directory from any subdirectory."""
    sub = git_repo / "sub"
    sub.mkdir()
    monkeypatch.chdir(sub)
    assert git_common_dir() == git_repo / ".git"
    assert git_common_dir(sub) == git_repo / ".git"


class _FakeResult:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout


@pytest.mark.parametrize("stdout", ["", "--path-format=absolute\n/r/.git", "a\nb"])
def test_git_common_dir_rejects_unexpected_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stdout: str
) -> None:
    """Empty or multi-line rev-parse output resolves to no common dir."""
    monkeypatch.setattr("gate_cache.snapshot.run_git", lambda *_a, **_k: _FakeResult(stdout))
    assert git_common_dir(tmp_path) is None


def test_git_common_dir_resolves_relative_output_against_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative common dir is resolved against the directory git ran in."""
    monkeypatch.setattr("gate_cache.snapshot.run_git", lambda *_a, **_k: _FakeResult("../.git"))
    sub = tmp_path / "sub"
    sub.mkdir()
    assert git_common_dir(sub) == tmp_path / ".git"
    monkeypatch.chdir(sub)
    assert git_common_dir() == tmp_path / ".git"


@pytest.mark.parametrize("at_root", [True, False])
def test_literal_pathspecs_still_find_untracked_files(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, at_root: bool
) -> None:
    """Untracked files are found whatever GIT_LITERAL_PATHSPECS says."""
    sub = git_repo / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("c\n")
    git("add", "sub/c.txt", cwd=git_repo)
    (git_repo / "elsewhere.txt").write_text("x\n")
    monkeypatch.setenv("GIT_LITERAL_PATHSPECS", "1")
    monkeypatch.chdir(git_repo if at_root else sub)
    assert take_snapshot().reason == "untracked file: elsewhere.txt"


def test_unknown_work_tree_root_is_unknown(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Inside the git directory there is no work tree to probe, so the tree is unknown."""
    monkeypatch.chdir(git_repo / ".git")
    assert take_snapshot().known is False
