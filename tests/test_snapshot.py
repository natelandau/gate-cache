"""Tests for snapshot detection."""

import os
import shutil
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from nclutils.sh import CompletedCommand, ShellCommandFailedError

from gate_cache import scratch, snapshot
from gate_cache.scratch import SCRATCH_PREFIX, runtime_area
from gate_cache.snapshot import git_common_dir, take_snapshot
from tests.conftest import add_submodule, expected_tree, git


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


def test_untracked_file_outside_cwd_is_hashed(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An untracked file anywhere in the repo is part of the tree taken from a subdirectory."""
    sub = git_repo / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("c\n")
    git("add", "sub/c.txt", cwd=git_repo)
    (git_repo / "elsewhere.txt").write_text("x\n")
    monkeypatch.chdir(sub)
    assert take_snapshot().tree == expected_tree(git_repo)


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
    assert take_snapshot().tree == expected_tree(git_repo)


def test_unknown_work_tree_root_is_unknown(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Inside the git directory there is no work tree to probe, so the tree is unknown."""
    monkeypatch.chdir(git_repo / ".git")
    assert take_snapshot().known is False


def _repo_with_module(git_repo: Path) -> Path:
    """Commit a tracked file in a module subdirectory and return that subdirectory."""
    module = git_repo / "api"
    module.mkdir()
    (module / "app.py").write_text("x = 1\n")
    git("add", "api/app.py", cwd=git_repo)
    git("commit", "-q", "-m", "add module", cwd=git_repo)
    return module


@pytest.mark.parametrize("linked", [False, True], ids=["main-checkout", "linked-worktree"])
def test_hook_git_dir_from_subdirectory_is_known(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, linked: bool
) -> None:
    """Verify GIT_DIR without GIT_WORK_TREE, as git sets for hooks, still finds the tree."""
    _repo_with_module(git_repo)
    root = git_repo
    if linked:
        root = tmp_path / "wt"
        git("worktree", "add", "-q", "--detach", str(root), cwd=git_repo)
    expected = take_snapshot(root).tree
    git_dir = git("rev-parse", "--absolute-git-dir", cwd=root)
    monkeypatch.setenv("GIT_DIR", git_dir)
    monkeypatch.chdir(root / "api")
    snapshot = take_snapshot()
    assert snapshot.reason is None
    assert snapshot.tree == expected


@pytest.mark.parametrize("linked", [False, True], ids=["main-checkout", "linked-worktree"])
def test_hook_git_dir_dirty_from_subdirectory_matches_root(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, linked: bool
) -> None:
    """Verify a hook in a subdirectory hashes edits and new files elsewhere in the repo."""
    _repo_with_module(git_repo)
    root = git_repo
    if linked:
        root = tmp_path / "wt"
        git("worktree", "add", "-q", "--detach", str(root), cwd=git_repo)
    (root / "a.txt").write_text("edited\n")
    (root / "new.txt").write_text("new\n")
    expected = expected_tree(root)
    monkeypatch.setenv("GIT_DIR", git("rev-parse", "--absolute-git-dir", cwd=root))
    monkeypatch.chdir(root / "api")
    snapshot = take_snapshot()
    assert snapshot.tree == expected
    assert snapshot.tree != git("rev-parse", "HEAD^{tree}", cwd=root)


def test_explicit_git_work_tree_is_respected(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify an explicit GIT_WORK_TREE is used as given."""
    module = _repo_with_module(git_repo)
    expected = take_snapshot(git_repo).tree
    monkeypatch.setenv("GIT_DIR", str(git_repo / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(git_repo))
    monkeypatch.chdir(module)
    assert take_snapshot().tree == expected


def test_core_worktree_config_is_left_to_git(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify a configured core.worktree is honored instead of a derived work tree."""
    module = _repo_with_module(git_repo)
    expected = take_snapshot(git_repo).tree
    git("config", "core.worktree", str(git_repo), cwd=git_repo)
    monkeypatch.setenv("GIT_DIR", str(git_repo / ".git"))
    monkeypatch.chdir(module)
    assert take_snapshot().tree == expected


def test_unreadable_git_dir_falls_back_to_inherited_env(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify an error while deriving the work tree leaves git's own behavior in place."""

    def unreadable(_cwd: Path | None) -> Path:
        raise PermissionError

    monkeypatch.setattr("gate_cache.snapshot._hook_work_tree", unreadable)
    assert take_snapshot().known


def test_skip_worktree_entry_is_unknown(git_repo: Path) -> None:
    """A skip-worktree entry hides edits, so the tree is unknown even when clean."""
    git("update-index", "--skip-worktree", "a.txt", cwd=git_repo)
    assert take_snapshot().reason == "skip-worktree or assume-unchanged entry: a.txt"


def test_assume_unchanged_entry_is_unknown(git_repo: Path) -> None:
    """An assume-unchanged entry hides edits, so the tree is unknown."""
    git("update-index", "--assume-unchanged", "a.txt", cwd=git_repo)
    (git_repo / "a.txt").write_text("hidden edit\n")
    assert take_snapshot().reason == "skip-worktree or assume-unchanged entry: a.txt"


def test_hidden_entry_reason_keeps_unusual_path(git_repo: Path) -> None:
    """Paths with spaces and non-ASCII characters print verbatim."""
    path = git_repo / "dir with space" / "é.txt"
    path.parent.mkdir()
    path.write_text("x\n")
    git("add", ".", cwd=git_repo)
    git("commit", "-q", "-m", "unusual", cwd=git_repo)
    git("update-index", "--skip-worktree", "dir with space/é.txt", cwd=git_repo)
    assert take_snapshot().reason == "skip-worktree or assume-unchanged entry: dir with space/é.txt"


def test_submodule_with_modified_content_is_unknown(git_repo: Path, tmp_path: Path) -> None:
    """Staged but uncommitted content inside a submodule makes the tree unknown."""
    sub = add_submodule(git_repo, tmp_path)
    (sub / "inner.txt").write_text("x\n")
    git("add", "inner.txt", cwd=sub)
    assert take_snapshot().reason == "submodule not at its index state: sub"


def test_submodule_with_untracked_file_is_unknown(git_repo: Path, tmp_path: Path) -> None:
    """An untracked file inside a submodule makes the tree unknown."""
    sub = add_submodule(git_repo, tmp_path)
    (sub / "loose.txt").write_text("x\n")
    assert take_snapshot().reason == "submodule not at its index state: sub"


def _moved_submodule_tree_is_honest(repo: Path, sub: Path) -> None:
    """Assert the snapshot is unknown or names the commit the submodule has checked out."""
    git(
        "-c", "user.name=Test", "-c", "user.email=test@example.com",
        "commit", "-q", "--allow-empty", "-m", "two",
        cwd=sub,
    )  # fmt: skip
    snap = take_snapshot()
    if snap.tree is not None:
        index = repo / ".git" / "honest-index"
        shutil.copy2(repo / ".git" / "index", index)
        env = {**os.environ, "GIT_INDEX_FILE": str(index)}
        head = git("rev-parse", "HEAD", cwd=sub)
        subprocess.run(  # noqa: S603
            ["git", "update-index", "--cacheinfo", f"160000,{head},sub"],  # noqa: S607
            cwd=repo,
            env=env,
            check=True,
        )
        honest = subprocess.run(
            ["git", "write-tree"],  # noqa: S607
            cwd=repo,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert snap.tree == honest


def test_moved_submodule_with_ignore_config_is_not_misnamed(git_repo: Path, tmp_path: Path) -> None:
    """Local ignore config cannot make the tree name a commit the submodule does not have."""
    sub = add_submodule(git_repo, tmp_path)
    git("config", "submodule.sub.ignore", "all", cwd=git_repo)
    git("config", "diff.ignoreSubmodules", "all", cwd=git_repo)
    _moved_submodule_tree_is_honest(git_repo, sub)


def test_moved_submodule_with_gitmodules_ignore_is_not_misnamed(
    git_repo: Path, tmp_path: Path
) -> None:
    """An ignore setting in .gitmodules, which makes `git add` keep the old commit, is caught."""
    sub = add_submodule(git_repo, tmp_path)
    git("config", "-f", ".gitmodules", "submodule.sub.ignore", "all", cwd=git_repo)
    git("add", ".gitmodules", cwd=git_repo)
    git("commit", "-q", "-m", "ignore sub", cwd=git_repo)
    _moved_submodule_tree_is_honest(git_repo, sub)
    assert take_snapshot().reason == "submodule not at its index state: sub"


def test_clean_submodule_is_known(git_repo: Path, tmp_path: Path) -> None:
    """A submodule at its recorded commit with no local changes keeps the tree known."""
    add_submodule(git_repo, tmp_path)
    snap = take_snapshot()
    assert snap.reason is None
    assert snap.tree == git("rev-parse", "HEAD^{tree}", cwd=git_repo)


def _object_files(repo: Path) -> set[Path]:
    """Return every file in the repo's object store."""
    return {path for path in (repo / ".git" / "objects").rglob("*") if path.is_file()}


def test_unstaged_change_hashes_working_copy(git_repo: Path) -> None:
    """An unstaged edit is keyed by the working copy content."""
    (git_repo / "a.txt").write_text("unstaged\n")
    snap = take_snapshot()
    assert snap.reason is None
    assert snap.tree == expected_tree(git_repo)
    assert snap.tree != git("rev-parse", "HEAD^{tree}", cwd=git_repo)


def test_untracked_file_hashes_working_copy(git_repo: Path) -> None:
    """An untracked, non-ignored file is part of the key."""
    (git_repo / "new.py").write_text("x = 1\n")
    snap = take_snapshot()
    assert snap.tree == expected_tree(git_repo)
    assert snap.tree != git("rev-parse", "HEAD^{tree}", cwd=git_repo)


def test_unstaged_deletion_hashes_working_copy(git_repo: Path) -> None:
    """A deleted tracked file matches the tree of a commit that deletes it."""
    (git_repo / "a.txt").unlink()
    tree = take_snapshot().tree
    git("rm", "-q", "a.txt", cwd=git_repo)
    git("commit", "-q", "-m", "delete", cwd=git_repo)
    assert tree == git("rev-parse", "HEAD^{tree}", cwd=git_repo)


def test_dirty_repo_without_commits_is_known(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_env: Path
) -> None:
    """A fresh repo with only untracked files still gets a tree."""
    repo = tmp_path / "fresh"
    repo.mkdir()
    git("init", "-q", cwd=repo)
    (repo / "new.txt").write_text("x\n")
    monkeypatch.chdir(repo)
    snap = take_snapshot()
    assert snap.reason is None
    assert snap.tree == expected_tree(repo)


def test_dirty_snapshot_leaves_real_index_unchanged(git_repo: Path) -> None:
    """Hashing dirty work never writes the real index."""
    (git_repo / "a.txt").write_text("unstaged\n")
    (git_repo / "new.txt").write_text("new\n")
    index = git_repo / ".git" / "index"
    before = (index.read_bytes(), index.stat().st_mtime_ns)
    assert take_snapshot().known
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before


def test_dirty_snapshot_writes_no_objects(git_repo: Path) -> None:
    """Hashing dirty work adds nothing to the repo's object store."""
    (git_repo / "a.txt").write_text("unstaged\n")
    (git_repo / "new.txt").write_text("new\n")
    before = _object_files(git_repo)
    assert take_snapshot().known
    assert _object_files(git_repo) == before


def test_dirty_snapshot_with_split_index_writes_nothing_in_git_dir(git_repo: Path) -> None:
    """Split index mode does not make the snapshot write a shared index into .git."""
    git("config", "core.splitIndex", "true", cwd=git_repo)
    git("update-index", "--split-index", cwd=git_repo)
    (git_repo / "a.txt").write_text("unstaged\n")
    (git_repo / "new.txt").write_text("new\n")
    before = set((git_repo / ".git").rglob("*"))
    assert take_snapshot().known
    assert set((git_repo / ".git").rglob("*")) == before


def test_inherited_index_file_is_honored(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A relative GIT_INDEX_FILE, as a commit hook can see, is read and left unchanged."""
    real = git_repo / ".git" / "index"
    alt = git_repo / ".git" / "alt-index"
    shutil.copy2(real, alt)
    (git_repo / "staged.txt").write_text("s\n")
    subprocess.run(
        ["git", "add", "staged.txt"],  # noqa: S607
        cwd=git_repo,
        env={**os.environ, "GIT_INDEX_FILE": str(alt)},
        check=True,
    )
    (git_repo / "a.txt").write_text("unstaged\n")
    expected = expected_tree(git_repo)
    before = (real.read_bytes(), alt.read_bytes())
    monkeypatch.setenv("GIT_INDEX_FILE", ".git/alt-index")
    snap = take_snapshot()
    assert snap.tree == expected
    assert (real.read_bytes(), alt.read_bytes()) == before


def test_ignored_file_does_not_change_dirty_hash(git_repo: Path) -> None:
    """A gitignored file stays out of the key on the dirty path too."""
    (git_repo / "a.txt").write_text("unstaged\n")
    before = take_snapshot().tree
    (git_repo / "ignored.txt").write_text("ignored\n")
    assert take_snapshot().tree == before


def test_scratch_dir_removed_after_snapshot(git_repo: Path) -> None:
    """A dirty snapshot leaves no scratch directory behind."""
    (git_repo / "a.txt").write_text("unstaged\n")
    assert take_snapshot().known
    assert list(runtime_area().glob(f"{SCRATCH_PREFIX}*")) == []


def test_scratch_dir_removed_after_git_failure(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A git failure while hashing dirty work is unknown and still cleans up."""
    real_run_git = snapshot.run_git

    def failing_run_git(*args: str, **kwargs: Any) -> CompletedCommand:
        env = kwargs.get("env") or {}
        if "write-tree" in args and SCRATCH_PREFIX in env.get("GIT_INDEX_FILE", ""):
            raise ShellCommandFailedError(msg="boom")
        return real_run_git(*args, **kwargs)

    monkeypatch.setattr(snapshot, "run_git", failing_run_git)
    (git_repo / "a.txt").write_text("unstaged\n")
    assert take_snapshot().reason == "could not hash working copy"
    assert list(runtime_area().glob(f"{SCRATCH_PREFIX}*")) == []


def test_unusable_scratch_area_is_unknown(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When the temp area cannot be used, dirty work runs uncached."""

    def denied() -> Path:
        msg = "denied"
        raise PermissionError(msg)

    monkeypatch.setattr(scratch, "runtime_area", denied)
    (git_repo / "a.txt").write_text("unstaged\n")
    assert take_snapshot().reason == "could not hash working copy"


def test_racy_clean_edit_is_hashed(git_repo: Path) -> None:
    """An edit that keeps size and mtime is still hashed when the index is racily clean."""
    git("config", "core.trustctime", "false", cwd=git_repo)
    git("config", "core.checkStat", "minimal", cwd=git_repo)
    path = git_repo / "a.txt"
    stamp = time.time() - 100
    path.write_text("aaa\n")
    os.utime(path, (stamp, stamp))
    git("add", "a.txt", cwd=git_repo)
    path.write_text("bbb\n")
    os.utime(path, (stamp, stamp))
    os.utime(git_repo / ".git" / "index", (stamp, stamp))
    assert take_snapshot().tree == expected_tree(git_repo)


def test_clean_snapshot_after_staging_leaves_real_index_unchanged(git_repo: Path) -> None:
    """Keying staged content never rewrites the real index or its cache-tree."""
    (git_repo / "a.txt").write_text("staged\n")
    git("add", "a.txt", cwd=git_repo)
    index = git_repo / ".git" / "index"
    before = (index.read_bytes(), index.stat().st_mtime_ns)
    tree = take_snapshot().tree
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before
    assert tree == expected_tree(git_repo)


def test_stale_stat_snapshot_leaves_real_index_unchanged(git_repo: Path) -> None:
    """A file touched without a content change neither dirties the key nor rewrites the index."""
    index = git_repo / ".git" / "index"
    path = git_repo / "a.txt"
    later = path.stat().st_mtime + 10
    os.utime(path, (later, later))
    before = (index.read_bytes(), index.stat().st_mtime_ns)
    assert take_snapshot().tree == git("rev-parse", "HEAD^{tree}", cwd=git_repo)
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before


def test_snapshot_does_not_block_on_held_index_lock(git_repo: Path) -> None:
    """A concurrent git command holding index.lock does not make a staged tree unknown."""
    (git_repo / "a.txt").write_text("staged\n")
    git("add", "a.txt", cwd=git_repo)
    expected = expected_tree(git_repo)
    lock = git_repo / ".git" / "index.lock"
    lock.write_text("")
    try:
        assert take_snapshot().tree == expected
    finally:
        lock.unlink()


def _commit_in(repo: Path, message: str) -> None:
    """Commit everything in a nested repo with a fixed identity."""
    git("add", "-A", cwd=repo)
    git(
        "-c", "user.name=Test", "-c", "user.email=test@example.com",
        "commit", "-q", "--allow-empty", "-m", message,
        cwd=repo,
    )  # fmt: skip


def test_untracked_file_counts_despite_show_untracked_config(git_repo: Path) -> None:
    """status.showUntrackedFiles=no cannot hide a new file from the key."""
    git("config", "status.showUntrackedFiles", "no", cwd=git_repo)
    before = take_snapshot().tree
    (git_repo / "new.py").write_text("x = 1\n")
    snap = take_snapshot()
    assert snap.tree == expected_tree(git_repo)
    assert snap.tree != before


def test_embedded_repo_with_edits_is_unknown(git_repo: Path) -> None:
    """An untracked nested repo with local edits cannot be described by its HEAD commit."""
    vendor = git_repo / "vendor"
    vendor.mkdir()
    git("init", "-q", cwd=vendor)
    (vendor / "lib.py").write_text("one\n")
    _commit_in(vendor, "one")
    (vendor / "lib.py").write_text("two\n")
    assert take_snapshot().reason == "submodule not at its index state: vendor"


def test_clean_embedded_repo_is_known(git_repo: Path) -> None:
    """A nested repo at its HEAD with no local changes is keyed by that commit."""
    vendor = git_repo / "vendor"
    vendor.mkdir()
    git("init", "-q", cwd=vendor)
    (vendor / "lib.py").write_text("one\n")
    _commit_in(vendor, "one")
    assert take_snapshot().reason is None


def test_submodule_untracked_file_hidden_by_its_config_is_unknown(
    git_repo: Path, tmp_path: Path
) -> None:
    """A submodule's own showUntrackedFiles=no cannot hide a new file inside it."""
    sub = add_submodule(git_repo, tmp_path)
    git("config", "status.showUntrackedFiles", "no", cwd=sub)
    (sub / "loose.txt").write_text("x\n")
    assert take_snapshot().reason == "submodule not at its index state: sub"


def test_submodule_assume_unchanged_entry_is_unknown(git_repo: Path, tmp_path: Path) -> None:
    """An assume-unchanged entry inside a submodule makes the tree unknown."""
    sub = add_submodule(git_repo, tmp_path)
    (sub / "lib.py").write_text("one\n")
    _commit_in(sub, "lib")
    git("add", "sub", cwd=git_repo)
    git("commit", "-q", "-m", "bump", cwd=git_repo)
    git("update-index", "--assume-unchanged", "lib.py", cwd=sub)
    (sub / "lib.py").write_text("hidden\n")
    assert take_snapshot().reason == "skip-worktree or assume-unchanged entry: sub/lib.py"


def test_gitlink_directory_without_repo_is_unknown(git_repo: Path, tmp_path: Path) -> None:
    """Plain files where a submodule should be are content the tree does not describe."""
    sub = add_submodule(git_repo, tmp_path)
    shutil.rmtree(sub)
    sub.mkdir()
    (sub / "lib.py").write_text("x\n")
    assert take_snapshot().reason == "submodule is not a checked-out repository: sub"


def test_submodule_content_is_unknown_despite_ignore_config(git_repo: Path, tmp_path: Path) -> None:
    """Ignore config cannot hide modified or untracked content inside a submodule."""
    sub = add_submodule(git_repo, tmp_path)
    git("config", "submodule.sub.ignore", "all", cwd=git_repo)
    git("config", "diff.ignoreSubmodules", "all", cwd=git_repo)
    (sub / "loose.txt").write_text("x\n")
    assert take_snapshot().reason == "submodule not at its index state: sub"


def test_skip_worktree_on_dirty_tree_is_unknown(git_repo: Path) -> None:
    """A hidden entry makes the tree unknown even when other files are dirty."""
    git("update-index", "--skip-worktree", "a.txt", cwd=git_repo)
    (git_repo / "new.txt").write_text("new\n")
    assert take_snapshot().reason == "skip-worktree or assume-unchanged entry: a.txt"


def test_relative_index_file_from_subdirectory(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative GIT_INDEX_FILE is read from the directory git runs in."""
    sub = git_repo / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("c\n")
    git("add", "sub/c.txt", cwd=git_repo)
    shutil.copy2(git_repo / ".git" / "index", git_repo / ".git" / "alt-index")
    git("reset", "-q", "sub/c.txt", cwd=git_repo)
    expected = git("rev-parse", "HEAD^{tree}", cwd=git_repo)
    (sub / "c.txt").unlink()
    sub.rmdir()
    sub.mkdir()
    monkeypatch.chdir(sub)
    monkeypatch.setenv("GIT_INDEX_FILE", "../.git/alt-index")
    # alt-index stages sub/c.txt, which is gone from disk, so the working copy is HEAD's tree.
    assert take_snapshot().tree == expected


def test_case_only_rename_is_unknown(git_repo: Path) -> None:
    """A rename that only changes case hides from git on a case-insensitive filesystem."""
    if not (git_repo / "A.TXT").exists():
        pytest.skip("needs a case-insensitive filesystem")
    (git_repo / "a.txt").rename(git_repo / "A.txt")
    assert take_snapshot().reason == "path differs from the index only by case: a.txt"


def test_file_ignored_only_case_insensitively_is_known(git_repo: Path) -> None:
    """A file that an exclude ignores only by matching case-insensitively is not a rename."""
    if not (git_repo / "A.TXT").exists():
        pytest.skip("needs a case-insensitive filesystem")
    (git_repo / ".gitignore").write_text("*.log\nbuild/\n")
    git("add", ".gitignore", cwd=git_repo)
    git("commit", "-q", "-m", "ignore", cwd=git_repo)
    (git_repo / "Debug.LOG").write_text("x\n")
    (git_repo / "Build").mkdir()
    (git_repo / "Build" / "out.txt").write_text("x\n")
    snap = take_snapshot()
    assert snap.reason is None
    assert snap.tree == git("rev-parse", "HEAD^{tree}", cwd=git_repo)


def test_embedded_repo_without_commit_names_git_error(git_repo: Path) -> None:
    """A nested repo with no commit cannot be staged, and the reason says why."""
    vendor = git_repo / "vendor"
    vendor.mkdir()
    git("init", "-q", cwd=vendor)
    reason = take_snapshot().reason
    assert reason is not None
    assert reason.startswith("could not stage working copy: ")
    assert "vendor" in reason


def test_hidden_entry_in_nested_submodule_is_unknown(git_repo: Path, tmp_path: Path) -> None:
    """Probing recurses, so a hidden entry two submodule levels down is still found."""
    sub = add_submodule(git_repo, tmp_path)
    inner = sub / "inner"
    inner.mkdir()
    git("init", "-q", cwd=inner)
    (inner / "x.txt").write_text("one\n")
    _commit_in(inner, "inner")
    _commit_in(sub, "embed inner")
    git("add", "sub", cwd=git_repo)
    git("commit", "-q", "-m", "bump", cwd=git_repo)
    git("update-index", "--assume-unchanged", "x.txt", cwd=inner)
    (inner / "x.txt").write_text("hidden\n")
    assert take_snapshot().reason == "skip-worktree or assume-unchanged entry: sub/inner/x.txt"


def test_uninitialized_submodule_is_unknown(git_repo: Path, tmp_path: Path) -> None:
    """An empty submodule directory gets content on init without changing the tree."""
    sub = add_submodule(git_repo, tmp_path)
    git("submodule", "deinit", "-q", "-f", "sub", cwd=git_repo)
    assert sub.is_dir()
    assert not any(sub.iterdir())
    assert take_snapshot().reason == "submodule is not checked out: sub"


def test_case_only_rename_of_force_added_ignored_file_is_unknown(git_repo: Path) -> None:
    """A tracked file that matches an ignore pattern is still caught when renamed by case."""
    if not (git_repo / "A.TXT").exists():
        pytest.skip("needs a case-insensitive filesystem")
    (git_repo / ".gitignore").write_text("ignored.txt\n*.log\n")
    (git_repo / "debug.log").write_text("kept\n")
    git("add", "-f", ".gitignore", "debug.log", cwd=git_repo)
    git("commit", "-q", "-m", "force-add log", cwd=git_repo)
    (git_repo / "debug.log").rename(git_repo / "Debug.log")
    assert take_snapshot().reason == "path differs from the index only by case: debug.log"
