"""Detect the git tree that a gate command is about to test."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from nclutils.git import run_git
from nclutils.sh import ShellCommandError, ShellCommandNotFoundError

from gate_cache import scratch


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


def _hook_work_tree(cwd: Path | None) -> Path | None:
    """Return the work tree that a GIT_DIR without GIT_WORK_TREE belongs to, if derivable.

    Git hands hooks GIT_DIR alone, and then takes the current directory for the top of the
    work tree. A hook that changes into a subdirectory would see every other file as changed.
    """
    git_dir = os.environ.get("GIT_DIR")
    if not git_dir or os.environ.get("GIT_WORK_TREE"):
        return None
    if run_git("config", "--get", "core.worktree", cwd=cwd, check=False).stdout.strip():
        return None
    base = Path(cwd) if cwd is not None else Path.cwd()
    path = (base / git_dir).resolve()
    # A linked worktree's git dir holds a `gitdir` file naming `<work tree>/.git`.
    gitdir_file = path / "gitdir"
    if gitdir_file.is_file():
        target = Path(gitdir_file.read_text(encoding="utf-8").strip())
        return (path / target).resolve().parent
    if path.name == ".git":
        return path.parent
    return None


def _git_env(cwd: Path | None) -> dict[str, str] | None:
    """Return an environment for gate-cache's own git probes, or None to inherit as is."""
    try:
        work_tree = _hook_work_tree(cwd)
    except OSError:
        return None
    if work_tree is None:
        return None
    return {**os.environ, "GIT_WORK_TREE": str(work_tree)}


def _work_tree_root(cwd: Path | None, env: dict[str, str] | None) -> Path | None:
    """Return the absolute top of the work tree, or None when there is none."""
    result = run_git("rev-parse", "--show-toplevel", cwd=cwd, env=env, check=False)
    output = result.stdout.strip()
    if result.returncode != 0 or not output or "\n" in output:
        return None
    return Path(output)


_GITLINK_MODE = "160000"


def _hidden_entry_reason(root: Path, env: dict[str, str] | None, label: str = "") -> str | None:
    """Return a reason when an index entry tells git to ignore edits to its file."""
    # `ls-files -v` tags assume-unchanged entries in lowercase and skip-worktree entries `S`.
    # Sparse checkout marks every path outside the cone skip-worktree, so it lands here too.
    output = run_git("ls-files", "-v", "-z", cwd=root, env=env).stdout
    for record in output.split("\0"):
        tag, _, path = record.partition(" ")
        if path and (tag.islower() or tag == "S"):
            return f"skip-worktree or assume-unchanged entry: {label}{path}"
    return None


@dataclass(frozen=True)
class _State:
    """Where the work tree is, or why no tree can describe it."""

    root: Path | None
    reason: str | None = None


@dataclass(frozen=True)
class _StatusRecord:
    """One entry of `git status --porcelain=v2`."""

    kind: str
    submodule: str
    path: str

    @property
    def submodule_moved(self) -> bool:
        """Return True when a submodule's commit, tracked content, or untracked files differ."""
        return self.submodule.startswith("S") and any(flag in self.submodule for flag in "CMU")


def _status(directory: Path, env: dict[str, str] | None) -> list[_StatusRecord]:
    """List every difference git status sees, regardless of status and submodule config."""
    # Optional locks off: status would otherwise refresh and rewrite the index it reads,
    # taking index.lock from a concurrent git command. `-unormal` and
    # `--ignore-submodules=none` override config that would hide untracked files and
    # submodule changes.
    output = run_git(
        "--no-optional-locks",
        "status",
        "--porcelain=v2",
        "-z",
        "--untracked-files=normal",
        "--ignore-submodules=none",
        cwd=directory,
        env=env,
    ).stdout
    found: list[_StatusRecord] = []
    records = iter(output.split("\0"))
    for record in records:
        kind = record[:1]
        if kind in {"1", "2"}:
            fields = record.split(" ", 9 if kind == "2" else 8)
            if kind == "2":
                next(records, None)  # a rename record is followed by its original path
            found.append(_StatusRecord(kind=kind, submodule=fields[2], path=fields[-1]))
        elif kind == "u":
            fields = record.split(" ", 10)
            found.append(_StatusRecord(kind=kind, submodule=fields[2], path=fields[-1]))
        elif kind == "?":
            found.append(_StatusRecord(kind=kind, submodule="N...", path=record[2:]))
    return found


def _gitlinks(directory: Path, env: dict[str, str] | None) -> list[str]:
    """Return the paths of every gitlink (submodule or embedded repo) in the index."""
    output = run_git("ls-files", "--stage", "-z", cwd=directory, env=env).stdout
    links: list[str] = []
    for record in output.split("\0"):
        info, _, path = record.partition("\t")
        if path and info.split(" ", 1)[0] == _GITLINK_MODE:
            links.append(path)
    return links


def _gitlink_reason(directory: Path, label: str, env: dict[str, str]) -> str | None:
    """Return why a submodule's checkout may hold content its recorded commit does not.

    The superproject's status runs the submodule's own status, which obeys the submodule's
    config and index flags, so each checkout is probed directly, recursively.
    """
    try:
        # An uninitialized submodule is an empty directory. `git submodule update --init`
        # later fills it without changing the tree, so an earlier pass proves nothing.
        if not (directory.is_dir() and any(directory.iterdir())):
            return f"submodule is not checked out: {label}"
        checked_out = (directory / ".git").exists()
    except OSError:
        checked_out = False
    if not checked_out:
        return f"submodule is not a checked-out repository: {label}"
    hidden = _hidden_entry_reason(directory, env, label=f"{label}/")
    if hidden:
        return hidden
    if _status(directory, env):
        return f"submodule not at its index state: {label}"
    nested = (
        _gitlink_reason(directory / path, f"{label}/{path}", env)
        for path in _gitlinks(directory, env)
    )
    return next((reason for reason in nested if reason), None)


def _inspect(cwd: Path | None, env: dict[str, str] | None) -> _State:
    """Probe the repository for anything that keeps one tree from describing the working copy."""
    if run_git("rev-parse", "--git-dir", cwd=cwd, env=env, check=False).returncode != 0:
        return _State(root=None, reason="not a git repository")
    # ls-files only lists paths under its cwd. Probing from the top avoids the `:/` pathspec,
    # which GIT_LITERAL_PATHSPECS turns into a literal path that matches nothing.
    root = _work_tree_root(cwd, env)
    if root is None:
        return _State(root=None, reason="could not locate work tree")
    if run_git("ls-files", "--unmerged", cwd=root, env=env).stdout:
        return _State(root=root, reason="unmerged index")
    return _State(root=root, reason=_hidden_entry_reason(root, env))


def _git_path(name: str, cwd: Path | None, env: dict[str, str] | None) -> Path:
    """Return the absolute path git uses for NAME, honoring GIT_INDEX_FILE and friends."""
    output = run_git("rev-parse", "--git-path", name, cwd=cwd, env=env).stdout.strip()
    if not output or "\n" in output:
        msg = f"unexpected `git rev-parse --git-path {name}` output: {output!r}"
        raise OSError(msg)
    path = Path(output)
    if path.is_absolute():
        return path
    return (Path(cwd) if cwd is not None else Path.cwd()) / path


def _require_private(env: dict[str, str], private: Path) -> None:
    """Refuse to run git unless its index and object store sit inside PRIVATE.

    The env is built a few lines earlier, so this never fires today. It stands between any
    future change to that env and a `git add -A` that would stage into the real index.
    """
    for key in ("GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"):
        if not Path(env[key]).resolve().is_relative_to(private.resolve()):
            msg = f"{key}={env[key]!r} is outside {private}"
            raise OSError(msg)


def _submodule_env(env: dict[str, str]) -> dict[str, str]:
    """Return ENV without the variables that tie git to the superproject's repository."""
    local = run_git("rev-parse", "--local-env-vars", env=env).stdout.split()
    return {key: value for key, value in env.items() if key not in local}


def _staged_reason(root: Path, env: dict[str, str]) -> str | None:
    """Return why the staged private index may not describe what the command reads."""
    links = _gitlinks(root, env)
    # Only gitlinks produce submodule records, so a repo without them skips a full status scan.
    if links:
        for record in _status(root, env):
            if record.submodule_moved:
                return f"submodule not at its index state: {record.path}"
        submodule_env = _submodule_env(env)
        for path in links:
            reason = _gitlink_reason(root / path, path, submodule_env)
            if reason:
                return reason
    ignorecase = run_git("config", "--bool", "core.ignorecase", cwd=root, env=env, check=False)
    if ignorecase.stdout.strip() == "true":
        return _case_mismatch_reason(root, env)
    return None


def _case_mismatch_reason(root: Path, env: dict[str, str]) -> str | None:
    """Return a reason when an indexed path is spelled differently on disk than in the index.

    On a case-insensitive filesystem a case-only rename keeps the old index entry, so the tree
    would name a path the command does not see. Comparing each path component with the real
    directory entries is exact and does not depend on ignore rules.
    """
    output = run_git("ls-files", "-z", cwd=root, env=env).stdout
    listings: dict[Path, set[str]] = {}
    for path in (entry for entry in output.split("\0") if entry):
        parent = root
        for part in path.split("/"):
            if parent not in listings:
                listings[parent] = {child.name for child in parent.iterdir()}
            if part not in listings[parent]:
                return f"path differs from the index only by case: {path}"
            parent = parent / part
    return None


def _private_snapshot(cwd: Path | None, root: Path, env: dict[str, str] | None) -> Snapshot:
    """Stage the working copy into a private index and return its tree, writing nothing real.

    A copy of the index and a throwaway object store take every write, so the real index,
    its lock, and `.git/objects` stay untouched even by write-tree's cache-tree update.
    """
    # Resolved from cwd, as git itself resolves an inherited relative GIT_INDEX_FILE.
    index = _git_path("index", cwd, env)
    objects = _git_path("objects", cwd, env)
    base = dict(os.environ if env is None else env)
    with scratch.scratch_dir() as private:
        private_index = private / "index"
        private_objects = private / "objects"
        # copy2 keeps the mtime git compares against to spot racily clean entries. A fresh
        # mtime would make git trust stat data for a file edited in the same second.
        if index.exists():
            shutil.copy2(index, private_index)
        private_objects.mkdir()
        alternates = [str(objects), base.get("GIT_ALTERNATE_OBJECT_DIRECTORIES", "")]
        private_env = {
            **base,
            "GIT_INDEX_FILE": str(private_index),
            "GIT_OBJECT_DIRECTORY": str(private_objects),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": os.pathsep.join(filter(None, alternates)),
        }
        _require_private(private_env, private)
        # Split index mode would write a shared index file into the real git directory.
        no_split = ("-c", "core.splitIndex=false")
        added = run_git(*no_split, "add", "-A", cwd=root, env=private_env, check=False)
        if added.returncode != 0:
            # Name git's complaint, such as an embedded repository with no commit, so the
            # user can see what keeps the cache off.
            lines = [line for line in added.stderr.splitlines() if line.strip()]
            errors = [line for line in lines if line.startswith(("fatal:", "error:"))]
            detail = (errors or lines or [None])[0]
            reason = "could not stage working copy"
            return Snapshot(tree=None, reason=f"{reason}: {detail}" if detail else reason)
        reason = _staged_reason(root, private_env)
        if reason:
            return Snapshot(tree=None, reason=reason)
        tree = run_git(*no_split, "write-tree", cwd=root, env=private_env).stdout
    return Snapshot(tree=tree, reason=None)


def take_snapshot(cwd: Path | None = None) -> Snapshot:
    """Identify the tree a gate command is about to test.

    The tree is the one a commit of the working copy would get, so a pass on uncommitted work
    matches the later commit. Every situation where the tree might not describe what the
    command reads, including any git failure, resolves to unknown so the caller runs the
    command uncached.

    Args:
        cwd: Directory to run git in. Defaults to the process working directory.

    Returns:
        A Snapshot holding the tree hash, or the reason it is unknown.
    """
    try:
        env = _git_env(cwd)
        state = _inspect(cwd, env)
    except ShellCommandNotFoundError:
        return Snapshot(tree=None, reason="git not found")
    except (ShellCommandError, UnicodeDecodeError):
        return Snapshot(tree=None, reason="could not inspect git state")
    if state.reason or state.root is None:
        return Snapshot(tree=None, reason=state.reason or "could not locate work tree")

    try:
        return _private_snapshot(cwd, state.root, env)
    except (ShellCommandError, OSError, UnicodeDecodeError):
        return Snapshot(tree=None, reason="could not hash working copy")


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
