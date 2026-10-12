"""Detect the git tree that a gate command is about to test."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nclutils.git import run_git
from nclutils.sh import ShellCommandError, ShellCommandNotFoundError


@dataclass(frozen=True)
class Snapshot:
    """The tree a gate is about to test, or why that tree is unknown.

    Attributes:
        tree: Git tree hash describing the content under test, or None when unknown.
        reason: Why the tree is unknown, or None when it is known.
    """

    tree: str | None
    reason: str | None

    @property
    def known(self) -> bool:
        """Return True when a tree hash identifies the content under test."""
        return self.tree is not None


def _work_tree_root(cwd: Path | None) -> Path | None:
    """Return the absolute top of the work tree, or None when there is none."""
    result = run_git("rev-parse", "--show-toplevel", cwd=cwd, check=False)
    output = result.stdout.strip()
    if result.returncode != 0 or not output or "\n" in output:
        return None
    return Path(output)


def _unknown_reason(cwd: Path | None) -> str | None:
    """Return why the working copy cannot be described by one tree, or None if it can."""
    if run_git("rev-parse", "--git-dir", cwd=cwd, check=False).returncode != 0:
        return "not a git repository"
    # ls-files only lists paths under its cwd. Probing from the top avoids the `:/` pathspec,
    # which GIT_LITERAL_PATHSPECS turns into a literal path that matches nothing.
    root = _work_tree_root(cwd)
    if root is None:
        return "could not locate work tree"
    if run_git("ls-files", "--unmerged", cwd=root).stdout:
        return "unmerged index"
    if run_git("diff", "--quiet", cwd=root, okay_codes=(0, 1)).returncode != 0:
        return "unstaged changes to tracked files"
    untracked = run_git("ls-files", "--others", "--exclude-standard", "-z", cwd=root).stdout
    if untracked:
        return f"untracked file: {untracked.split(chr(0))[0]}"
    return None


def take_snapshot(cwd: Path | None = None) -> Snapshot:
    """Identify the tree a gate command is about to test.

    The snapshot is known only when the working copy matches the index for tracked files and
    no untracked, non-ignored files exist. Every other situation, including any git failure,
    resolves to unknown so the caller runs the command uncached.

    Args:
        cwd: Directory to run git in. Defaults to the process working directory.

    Returns:
        A Snapshot holding the tree hash, or the reason it is unknown.
    """
    try:
        reason = _unknown_reason(cwd)
    except ShellCommandNotFoundError:
        return Snapshot(tree=None, reason="git not found")
    except (ShellCommandError, UnicodeDecodeError):
        return Snapshot(tree=None, reason="could not inspect git state")
    if reason:
        return Snapshot(tree=None, reason=reason)

    try:
        tree = run_git("write-tree", cwd=cwd).stdout
    except (ShellCommandError, UnicodeDecodeError):
        return Snapshot(tree=None, reason="could not compute tree")
    return Snapshot(tree=tree, reason=None)


def git_common_dir(cwd: Path | None = None) -> Path | None:
    """Return the absolute git common directory shared by all linked worktrees.

    Args:
        cwd: Directory to run git in. Defaults to the process working directory.

    Returns:
        The absolute path, or None when git fails or its output is not a single path.
    """
    try:
        result = run_git("rev-parse", "--git-common-dir", cwd=cwd)
    except (ShellCommandError, UnicodeDecodeError):
        return None
    output = result.stdout.strip()
    if not output or "\n" in output:
        return None
    path = Path(output)
    if path.is_absolute():
        return path
    try:
        base = Path(cwd) if cwd is not None else Path.cwd()
        return (base / path).resolve()
    except (OSError, RuntimeError):
        return None
